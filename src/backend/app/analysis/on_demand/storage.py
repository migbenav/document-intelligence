"""Persistence layer for on-demand analysis results in Supabase.

Provides get, upsert, status summary, and mark_all_outdated operations
for the analysis_results table. Uses upsert semantics on the
(document_id, analysis_type) UNIQUE constraint.

Requirements covered: Req 6 (criteria 3, 5, 6), Req 7 (criteria 6, 7).
"""

import logging
from datetime import datetime, timezone

from app.analysis.on_demand.models import (
    AnalysisRecord,
    AnalysisStatus,
    AnalysisType,
)

logger = logging.getLogger(__name__)

TABLE_NAME = "analysis_results"


class OnDemandAnalysisStorage:
    """Persistence for on-demand analysis results in Supabase.

    Wraps the Supabase client to provide a clean interface for
    analysis result CRUD operations. One result per (document_id, analysis_type)
    combination, enforced by the UNIQUE constraint.
    """

    def __init__(self, supabase_client) -> None:
        """Initialize with a Supabase client instance.

        Args:
            supabase_client: An initialized Supabase client for DB access.
        """
        self._client = supabase_client

    async def get_result(
        self, document_id: str, analysis_type: AnalysisType
    ) -> AnalysisRecord | None:
        """Retrieve the analysis result for a given document and type.

        Args:
            document_id: The document UUID to look up.
            analysis_type: The analysis type to look up.

        Returns:
            AnalysisRecord if found, None if no result exists.
        """
        result = (
            self._client.table(TABLE_NAME)
            .select("*")
            .eq("document_id", document_id)
            .eq("analysis_type", analysis_type.value)
            .execute()
        )

        if not result.data:
            return None

        return self._row_to_record(result.data[0])

    async def save_result(self, record: AnalysisRecord) -> None:
        """Insert or update an analysis result.

        Uses upsert semantics on the (document_id, analysis_type) UNIQUE
        constraint to ensure one result per type per document.

        Args:
            record: The AnalysisRecord to persist.
        """
        now = datetime.now(timezone.utc).isoformat()

        db_record = {
            "document_id": record.document_id,
            "analysis_type": record.analysis_type.value,
            "status": record.status.value,
            "result": record.result,
            "model_id": record.model_id,
            "prompt_version": record.prompt_version,
            "error_message": record.error_message,
            "updated_at": now,
        }

        self._client.table(TABLE_NAME).upsert(
            db_record, on_conflict="document_id,analysis_type"
        ).execute()

    async def get_all_statuses(self, document_id: str) -> dict[str, dict]:
        """Get the status summary for all analysis types of a document.

        Returns entries for ALL 4 analysis types. Types that have no
        stored row default to status "not_started" with updated_at=None.

        Args:
            document_id: The document UUID to query.

        Returns:
            Dict mapping analysis type value to {status, updated_at} dict.
            Example: {"build_index": {"status": "completed", "updated_at": "..."}, ...}
        """
        result = (
            self._client.table(TABLE_NAME)
            .select("analysis_type, status, updated_at")
            .eq("document_id", document_id)
            .execute()
        )

        # Build a map from existing rows
        existing: dict[str, dict] = {}
        for row in result.data:
            existing[row["analysis_type"]] = {
                "status": row["status"],
                "updated_at": row["updated_at"],
            }

        # Fill all 4 types, defaulting missing ones to "not_started"
        statuses: dict[str, dict] = {}
        for analysis_type in AnalysisType:
            if analysis_type.value in existing:
                statuses[analysis_type.value] = existing[analysis_type.value]
            else:
                statuses[analysis_type.value] = {
                    "status": AnalysisStatus.NOT_STARTED.value,
                    "updated_at": None,
                }

        return statuses

    async def mark_all_outdated(self, document_id: str) -> None:
        """Mark all analysis results for a document as outdated.

        Sets status='outdated' and updates the updated_at timestamp
        for all rows matching the document_id. No-op if no results exist.

        Args:
            document_id: The document whose results should be marked outdated.
        """
        now = datetime.now(timezone.utc).isoformat()

        self._client.table(TABLE_NAME).update(
            {"status": AnalysisStatus.OUTDATED.value, "updated_at": now}
        ).eq("document_id", document_id).execute()

    def _row_to_record(self, row: dict) -> AnalysisRecord:
        """Convert a database row dict to an AnalysisRecord model.

        Args:
            row: Dict from Supabase query result.

        Returns:
            A validated AnalysisRecord instance.
        """
        return AnalysisRecord(
            id=str(row["id"]),
            document_id=str(row["document_id"]),
            analysis_type=AnalysisType(row["analysis_type"]),
            status=AnalysisStatus(row["status"]),
            result=row.get("result"),
            model_id=row.get("model_id"),
            prompt_version=row.get("prompt_version"),
            error_message=row.get("error_message"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
