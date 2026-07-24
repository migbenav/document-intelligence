"""Intermediate representation assembly."""

from app.models.document import (
    ContentChunkModel,
    DocumentMetadata,
    IntermediateRepresentation,
)


class IRBuilder:
    """Assembles and validates an IntermediateRepresentation from ingested components."""

    def build(
        self,
        document_id: str,
        metadata: DocumentMetadata,
        chunks: list[ContentChunkModel],
    ) -> IntermediateRepresentation:
        """Build an IntermediateRepresentation after validating chunk constraints.

        Validates:
            1. Sequential chunk ordering — chunk.order values must be 0, 1, 2, ... with no gaps.
            2. Unique chunk_ids — no duplicate chunk_id values across chunks.

        Args:
            document_id: Unique identifier for this ingestion session.
            metadata: Document-level metadata populated during ingestion.
            chunks: Ordered list of content chunks extracted from the document.

        Returns:
            A validated IntermediateRepresentation instance.

        Raises:
            ValueError: If chunk ordering is non-sequential or chunk_ids are not unique.
        """
        self._validate_chunk_ordering(chunks)
        self._validate_unique_chunk_ids(chunks)

        return IntermediateRepresentation(
            document_id=document_id,
            metadata=metadata,
            chunks=chunks,
        )

    def _validate_chunk_ordering(self, chunks: list[ContentChunkModel]) -> None:
        """Validate that chunk order values are strictly sequential starting from 0."""
        for expected_order, chunk in enumerate(chunks):
            if chunk.order != expected_order:
                raise ValueError(
                    f"Chunk ordering is not sequential: expected order {expected_order}, "
                    f"got {chunk.order} for chunk_id '{chunk.chunk_id}'"
                )

    def _validate_unique_chunk_ids(self, chunks: list[ContentChunkModel]) -> None:
        """Validate that all chunk_ids are unique across the chunk list."""
        seen_ids: set[str] = set()
        for chunk in chunks:
            if chunk.chunk_id in seen_ids:
                raise ValueError(
                    f"Duplicate chunk_id found: '{chunk.chunk_id}'"
                )
            seen_ids.add(chunk.chunk_id)
