"""Persistence layer for DocumentCard in Supabase.

Provides get, upsert, and mark_outdated operations for the document_cards
table. Uses upsert semantics on the document_id UNIQUE constraint to prevent
duplicate cards.

Requirements covered: Req 4 (criteria 1, 3, 4), Req 6 (criteria 1, 3).
"""

import logging
from datetime import datetime, timezone

from app.models.document_card import (
    DocumentCard,
    DocumentCardStatistics,
    DocumentClassification,
    FileMetadata,
    OrganizationType,
)

logger = logging.getLogger(__name__)


class BaseAnalysisStorage:
    """Persistence for DocumentCard in Supabase.

    Wraps the Supabase client to provide a clean interface for card
    CRUD operations. One card per document (UNIQUE on document_id).
    """

    def __init__(self, supabase_client) -> None:
        """Initialize with a Supabase client instance.

        Args:
            supabase_client: An initialized Supabase client for DB access.
        """
        self._client = supabase_client

    async def get_card(self, document_id: str) -> DocumentCard | None:
        """Retrieve the DocumentCard for a given document.

        Args:
            document_id: The document UUID to look up.

        Returns:
            DocumentCard if found, None if no card exists for this document.
        """
        result = (
            self._client.table("document_cards")
            .select("*")
            .eq("document_id", document_id)
            .execute()
        )

        if not result.data:
            return None

        return self._row_to_card(result.data[0])

    async def upsert_card(self, card: DocumentCard) -> None:
        """Insert or update a DocumentCard.

        Uses upsert semantics on the document_id UNIQUE constraint.
        Always resets outdated to False on upsert (Req 6 criterion 3).

        Args:
            card: The DocumentCard to persist.
        """
        now = datetime.now(timezone.utc).isoformat()

        record = {
            "document_id": card.document_id,
            "title": card.title,
            "summary": card.summary,
            "classification": card.classification.value if card.classification else None,
            "organization_type": card.organization_type.value,
            "statistics": card.statistics.model_dump(mode="json"),
            "file_metadata": card.file_metadata.model_dump(mode="json"),
            "status": card.status,
            "outdated": False,
            "model_id": card.model_id,
            "prompt_version": card.prompt_version,
            "updated_at": now,
        }

        self._client.table("document_cards").upsert(
            record, on_conflict="document_id"
        ).execute()

    async def mark_outdated(self, document_id: str) -> None:
        """Mark the existing card as outdated.

        Sets outdated=True and updates the updated_at timestamp.
        No-op if no card exists for the document.

        Args:
            document_id: The document whose card should be marked outdated.
        """
        now = datetime.now(timezone.utc).isoformat()

        self._client.table("document_cards").update(
            {"outdated": True, "updated_at": now}
        ).eq("document_id", document_id).execute()

    def _row_to_card(self, row: dict) -> DocumentCard:
        """Convert a database row dict to a DocumentCard model.

        Args:
            row: Dict from Supabase query result.

        Returns:
            A validated DocumentCard instance.
        """
        # Parse classification enum (nullable)
        classification = None
        if row.get("classification"):
            classification = DocumentClassification(row["classification"])

        # Parse statistics from JSONB
        statistics = DocumentCardStatistics.model_validate(row["statistics"])

        # Parse file_metadata from JSONB
        file_metadata = FileMetadata.model_validate(row["file_metadata"])

        return DocumentCard(
            id=str(row["id"]),
            document_id=str(row["document_id"]),
            title=row["title"],
            summary=row.get("summary"),
            classification=classification,
            organization_type=OrganizationType(row["organization_type"]),
            statistics=statistics,
            file_metadata=file_metadata,
            status=row["status"],
            outdated=row.get("outdated", False),
            model_id=row.get("model_id"),
            prompt_version=row.get("prompt_version"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
