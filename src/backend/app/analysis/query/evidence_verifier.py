"""Evidence verification for natural language query source references.

Verifies that each QuerySourceRef's evidence text span actually exists in the
document's Intermediate Representation (IR). Reuses the deterministic
text-matching algorithm from the existing VerificationService.

No LLM calls — purely deterministic (Req 4.1).
"""

from app.analysis.verification import _fuzzy_match, _normalize_whitespace
from app.models.document import IntermediateRepresentation
from app.models.query import QuerySourceRef


class QueryEvidenceVerifier:
    """Verifies query source_ref evidence against the IR.

    Uses the same 3-step algorithm as VerificationService:
    1. Normalize whitespace in evidence text.
    2. Exact substring match in referenced chunk_id.
    3. Exact substring match in any IR chunk.
    4. Fuzzy match (80% threshold) in any chunk.

    Sets evidence_verified on each source_ref.
    Does NOT call the LLM — purely deterministic.
    """

    def __init__(self, fuzzy_threshold: float = 0.8) -> None:
        self._fuzzy_threshold = fuzzy_threshold

    def verify(
        self,
        source_refs: list[QuerySourceRef],
        ir: IntermediateRepresentation,
    ) -> list[QuerySourceRef]:
        """Verify each source_ref's evidence text against IR chunks.

        Args:
            source_refs: List of source references to verify.
            ir: The Intermediate Representation containing source chunks.

        Returns:
            The same list of source_refs with evidence_verified set on each.
        """
        # Build chunk_map (chunk_id → normalized text) and list of all normalized chunks
        chunk_map: dict[str, str] = {}
        normalized_chunks: list[str] = []

        for chunk in ir.chunks:
            normalized_text = _normalize_whitespace(chunk.text)
            chunk_map[chunk.chunk_id] = normalized_text
            normalized_chunks.append(normalized_text)

        # Verify each source_ref
        for source_ref in source_refs:
            normalized_evidence = _normalize_whitespace(source_ref.evidence)

            # Edge case: empty evidence → mark as unverified without running algorithm
            if not normalized_evidence:
                source_ref.evidence_verified = False
                continue

            # Run 3-step verification algorithm
            found = self._check_evidence(
                normalized_evidence,
                source_ref.chunk_id,
                chunk_map,
                normalized_chunks,
            )
            source_ref.evidence_verified = found

        return source_refs

    def _check_evidence(
        self,
        normalized_evidence: str,
        referenced_chunk_id: str,
        chunk_map: dict[str, str],
        normalized_chunks: list[str],
    ) -> bool:
        """Check if evidence exists in the IR using the 3-step algorithm.

        Steps:
        1. Exact substring match in the referenced chunk_id.
        2. Exact substring match in any IR chunk.
        3. Fuzzy match (threshold) in any chunk.

        Edge case: if chunk_id not in IR, skip step 1 and proceed with full-IR matching.
        """
        # Step 1: Exact substring match in the referenced chunk
        referenced_text = chunk_map.get(referenced_chunk_id)
        if referenced_text is not None and normalized_evidence in referenced_text:
            return True

        # Step 2: Exact substring match in any chunk
        for chunk_text in normalized_chunks:
            if normalized_evidence in chunk_text:
                return True

        # Step 3: Fuzzy match in any chunk
        for chunk_text in normalized_chunks:
            if _fuzzy_match(normalized_evidence, chunk_text, self._fuzzy_threshold):
                return True

        return False
