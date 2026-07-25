"""Analysis pipeline orchestrator.

Coordinates type inference, extraction, and verification to produce a
Knowledge Model from a document's Intermediate Representation.

Requirements covered: 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.7, 10.2, 10.4
"""

import logging
from datetime import datetime, timezone

from app.analysis.extraction import ExtractionService
from app.analysis.type_inference import TypeInferenceService
from app.analysis.verification import VerificationService
from app.models.knowledge_model import AnalysisSession

logger = logging.getLogger(__name__)

# Valid document types (Req 4.5)
VALID_DOCUMENT_TYPES = {"prd", "technical_spec", "policy_process", "generic"}


# --- Custom Errors ---


class DocumentNotFoundError(Exception):
    """Raised when the specified document does not exist."""

    pass


class DocumentNotReadyError(Exception):
    """Raised when the document is not in 'ready' status (ingestion incomplete)."""

    pass


class AnalysisAlreadyExistsError(Exception):
    """Raised when an analysis session already exists for this document."""

    pass


class InvalidSessionStateError(Exception):
    """Raised when the session is not in the expected state for the operation."""

    pass


class InvalidDocumentTypeError(Exception):
    """Raised when an invalid document type value is provided."""

    def __init__(self, invalid_type: str):
        self.invalid_type = invalid_type
        self.valid_types = sorted(VALID_DOCUMENT_TYPES)
        super().__init__(
            f"Invalid document type '{invalid_type}'. "
            f"Valid types are: {', '.join(self.valid_types)}"
        )


class AnalysisStorageService:
    """Storage interface for analysis session persistence.

    Wraps the Supabase client to provide a clean interface for the
    AnalysisService. This abstraction allows tests to mock storage
    without depending on the Supabase client internals.
    """

    def __init__(self, supabase_client) -> None:
        self._client = supabase_client

    def get_document(self, document_id: str) -> dict | None:
        """Get a document record by ID.

        Returns the document row as a dict, or None if not found.
        """
        result = (
            self._client.table("documents")
            .select("*")
            .eq("document_id", document_id)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]

    def get_ir(self, document_id: str) -> dict | None:
        """Get document chunks for building the IR.

        Returns a list of chunk dicts ordered by position, or None if not found.
        """
        result = (
            self._client.table("document_chunks")
            .select("*")
            .eq("document_id", document_id)
            .order("order")
            .execute()
        )
        if not result.data:
            return None
        return result.data

    def create_session(self, document_id: str) -> dict:
        """Create a new analysis session record.

        Returns the created session row as a dict.
        """
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "document_id": document_id,
            "status": "inferring_type",
            "created_at": now,
            "updated_at": now,
        }
        result = self._client.table("analysis_sessions").insert(record).execute()
        return result.data[0]

    def update_session(self, session_id: str, **fields) -> dict:
        """Update session fields.

        Returns the updated session row as a dict.
        """
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = (
            self._client.table("analysis_sessions")
            .update(fields)
            .eq("id", session_id)
            .execute()
        )
        return result.data[0]

    def get_session_by_document(self, document_id: str) -> dict | None:
        """Get the analysis session for a document.

        Returns the session row as a dict, or None if no session exists.
        """
        result = (
            self._client.table("analysis_sessions")
            .select("*")
            .eq("document_id", document_id)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]


class AnalysisService:
    """Orchestrates the full analysis pipeline.

    Pipeline steps:
    1. start_analysis: validates document state, creates session, runs type inference
    2. confirm_and_extract: validates session state, runs extraction + verification

    On failure at any step, the session is marked as failed with cleanup (Req 8.4).
    No user metadata is stored alongside results (Req 10.4).
    """

    def __init__(
        self,
        type_inference_service: TypeInferenceService,
        extraction_service: ExtractionService,
        verification_service: VerificationService,
        storage: AnalysisStorageService,
    ) -> None:
        """Initialize with all pipeline dependencies.

        Args:
            type_inference_service: Service for document type inference.
            extraction_service: Service for Knowledge Model extraction.
            verification_service: Service for evidence verification.
            storage: Storage interface for persistence.
        """
        self._type_inference = type_inference_service
        self._extraction = extraction_service
        self._verification = verification_service
        self._storage = storage

    async def start_analysis(self, document_id: str) -> AnalysisSession:
        """Initiate analysis for a document.

        Validates the document exists and is ready, creates an analysis session,
        retrieves the IR, runs type inference, and returns the session in
        "awaiting_confirmation" status.

        Args:
            document_id: The document to analyze.

        Returns:
            AnalysisSession with suggested type and justification.

        Raises:
            DocumentNotFoundError: Document does not exist.
            DocumentNotReadyError: Document is not in 'ready' status (Req 9.1).
            AnalysisAlreadyExistsError: Analysis session already exists (Req 9.7).
        """
        # Verify document exists
        document = self._storage.get_document(document_id)
        if document is None:
            raise DocumentNotFoundError(
                f"Document '{document_id}' not found."
            )

        # Verify document is in "ready" status (Req 9.1)
        if document.get("status") != "ready":
            raise DocumentNotReadyError(
                f"Document '{document_id}' is not ready for analysis. "
                f"Current status: {document.get('status')}"
            )

        # Verify no existing analysis session (Req 9.7)
        existing_session = self._storage.get_session_by_document(document_id)
        if existing_session is not None:
            raise AnalysisAlreadyExistsError(
                f"Analysis already exists for document '{document_id}'."
            )

        # Create session with status "inferring_type" (Req 8.1)
        session_row = self._storage.create_session(document_id)
        session_id = session_row["id"]

        try:
            # Retrieve IR from storage
            ir = await self._get_ir(document_id)

            # Call type inference (Req 3.4 — system waits for confirmation)
            suggestion = await self._type_inference.infer(ir)

            # Update session with suggestion and set status to "awaiting_confirmation" (Req 8.2)
            updated_row = self._storage.update_session(
                session_id,
                status="awaiting_confirmation",
                suggested_type=suggestion.suggested_type,
                suggested_type_justification=suggestion.justification,
            )

            return self._row_to_session(updated_row)

        except Exception as e:
            # Failure handling: mark session as failed (Req 8.4)
            self._mark_failed(session_id, f"Type inference failed: {e}")
            raise

    async def confirm_and_extract(
        self, document_id: str, document_type: str
    ) -> AnalysisSession:
        """Confirm document type and run extraction + verification.

        Validates the session is in the correct state, validates the document type,
        runs extraction and verification, and persists the completed Knowledge Model.

        Args:
            document_id: The document to extract from.
            document_type: The confirmed document type.

        Returns:
            AnalysisSession with status "completed" and persisted KM.

        Raises:
            DocumentNotFoundError: Document/session does not exist.
            InvalidSessionStateError: Session not in 'awaiting_confirmation' (Req 4.4).
            InvalidDocumentTypeError: Invalid type value (Req 4.5).
        """
        # Validate document_type is a valid value (Req 4.5)
        if document_type not in VALID_DOCUMENT_TYPES:
            raise InvalidDocumentTypeError(document_type)

        # Get the session
        session_row = self._storage.get_session_by_document(document_id)
        if session_row is None:
            raise DocumentNotFoundError(
                f"No analysis session found for document '{document_id}'."
            )

        session_id = session_row["id"]

        # Validate session is in "awaiting_confirmation" state (Req 4.4)
        if session_row["status"] != "awaiting_confirmation":
            raise InvalidSessionStateError(
                f"Session is in '{session_row['status']}' state. "
                f"Expected 'awaiting_confirmation' to confirm type."
            )

        try:
            # Record confirmed_type and set status to "extracting" (Req 4.1)
            self._storage.update_session(
                session_id,
                status="extracting",
                confirmed_type=document_type,
            )

            # Retrieve IR
            ir = await self._get_ir(document_id)

            # Call extraction (Req 5.1)
            knowledge_model = await self._extraction.extract(ir, document_type)

            # Update status to "verifying"
            self._storage.update_session(session_id, status="verifying")

            # Call verification (Req 7)
            verification_result = self._verification.verify(knowledge_model, ir)

            # Update extraction_metadata with verification_rate
            knowledge_model.extraction_metadata.verification_rate = (
                verification_result.verification_rate
            )

            # Persist completed KM + metadata (Req 8.3)
            # No user metadata stored (Req 10.4) — only document content derivatives
            km_data = knowledge_model.model_dump(mode="json")
            metadata_data = knowledge_model.extraction_metadata.model_dump(mode="json")

            updated_row = self._storage.update_session(
                session_id,
                status="completed",
                knowledge_model=km_data,
                extraction_metadata=metadata_data,
                prompt_version=knowledge_model.extraction_metadata.prompt_version,
                model_id=knowledge_model.extraction_metadata.model_id,
            )

            return self._row_to_session(updated_row)

        except Exception as e:
            # Failure handling: mark session as failed and clean up (Req 8.4)
            self._mark_failed(
                session_id,
                f"Analysis failed during extraction/verification: {e}",
            )
            raise

    async def get_knowledge_model(self, document_id: str) -> dict | None:
        """Retrieve the Knowledge Model for a completed analysis.

        Args:
            document_id: The document to get the KM for.

        Returns:
            The Knowledge Model dict if analysis is completed, None otherwise.
        """
        session_row = self._storage.get_session_by_document(document_id)
        if session_row is None:
            return None
        if session_row["status"] != "completed":
            return None
        return session_row.get("knowledge_model")

    async def get_session(self, document_id: str) -> AnalysisSession | None:
        """Retrieve the analysis session for a document.

        Args:
            document_id: The document to get the session for.

        Returns:
            AnalysisSession if found, None otherwise.
        """
        session_row = self._storage.get_session_by_document(document_id)
        if session_row is None:
            return None
        return self._row_to_session(session_row)

    async def _get_ir(self, document_id: str):
        """Retrieve the full IR for a document.

        Imports and uses the ingestion StorageService pattern to reconstruct
        the IntermediateRepresentation from database records.
        """
        import json

        from app.models.document import (
            ContentChunkModel,
            DetectedLanguage,
            DocumentFormat,
            DocumentMetadata,
            IntermediateRepresentation,
        )

        # Get document record
        doc = self._storage.get_document(document_id)
        if doc is None:
            raise DocumentNotFoundError(f"Document '{document_id}' not found.")

        # Get chunks
        chunks_data = self._storage.get_ir(document_id)
        if chunks_data is None:
            chunks_data = []

        # Parse warnings
        warnings = doc.get("warnings", [])
        if isinstance(warnings, str):
            warnings = json.loads(warnings)

        metadata = DocumentMetadata(
            original_filename=doc["original_filename"],
            format=DocumentFormat(doc["format"]),
            size_bytes=doc["size_bytes"],
            language=DetectedLanguage(doc.get("language", "unknown")),
            upload_timestamp=datetime.fromisoformat(doc["upload_timestamp"]),
            warnings=warnings,
        )

        chunks = [
            ContentChunkModel(
                chunk_id=c["chunk_id"],
                text=c["text"],
                structural_context=(
                    json.loads(c["structural_context"])
                    if isinstance(c["structural_context"], str)
                    else c["structural_context"]
                ),
                order=c["order"],
            )
            for c in chunks_data
        ]

        return IntermediateRepresentation(
            document_id=document_id,
            metadata=metadata,
            chunks=chunks,
        )

    def _mark_failed(self, session_id: str, error_message: str) -> None:
        """Mark a session as failed with cleanup (Req 8.4).

        Sets status to 'failed', records the error message, and clears any
        partial knowledge_model data to ensure no incomplete KM is retrievable.
        """
        try:
            self._storage.update_session(
                session_id,
                status="failed",
                error_message=error_message,
                knowledge_model=None,  # Clean up partial data (Req 8.4)
                extraction_metadata=None,
            )
        except Exception as cleanup_error:
            logger.error(
                "Failed to mark session as failed: %s",
                cleanup_error,
                extra={"session_id": session_id, "original_error": error_message},
            )

    def _row_to_session(self, row: dict) -> AnalysisSession:
        """Convert a database row dict to an AnalysisSession model."""
        return AnalysisSession(
            id=str(row["id"]),
            document_id=str(row["document_id"]),
            status=row["status"],
            suggested_type=row.get("suggested_type"),
            suggested_type_justification=row.get("suggested_type_justification"),
            confirmed_type=row.get("confirmed_type"),
            error_message=row.get("error_message"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
