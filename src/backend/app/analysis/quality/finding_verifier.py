"""Finding evidence verifier for quality analysis.

Verifies that each quality finding's source_ref.evidence text span
actually exists in the document's Intermediate Representation (IR).
Reuses the same deterministic text-matching algorithm from VerificationService
(Feature 3, Req 7.5): normalize whitespace → exact match in referenced chunk →
exact match in any chunk → fuzzy match (80% threshold) in any chunk.

This module does NOT call the LLM — purely deterministic (Req 7.5).

Validates: Requirements 7.1, 7.2, 7.3, 7.5, 7.6, 7.7
"""

from app.analysis.verification import _fuzzy_match, _normalize_whitespace
from app.models.document import IntermediateRepresentation
from app.models.quality_analysis import FindingSourceRef, Inconsistency, Suggestion


class FindingVerifier:
    """Verifies evidence text spans in quality findings against the IR.

    Uses the same verification algorithm as VerificationService (Feature 3):
    1. Normalize whitespace on the evidence text.
    2. Exact substring match in the referenced chunk_id.
    3. Exact substring match in any IR chunk.
    4. Fuzzy match (80% similarity threshold) in any chunk.

    MissingElement findings are NOT verified — they have no source_ref
    by definition (Req 7.4).
    """

    def __init__(self, fuzzy_threshold: float = 0.8) -> None:
        self._fuzzy_threshold = fuzzy_threshold

    def verify_all(
        self,
        inconsistencies: list[Inconsistency],
        suggestions: list[Suggestion],
        ir: IntermediateRepresentation,
    ) -> tuple[list[Inconsistency], list[Suggestion]]:
        """Verify source_ref evidence in all findings against the IR.

        For each source_ref in each finding:
        - Sets evidence_verified = True if evidence matches the IR text.
        - Sets evidence_verified = False if no match is found.

        For each finding:
        - Sets all_evidence_unverified = True if ALL source_refs have
          evidence_verified = False.

        Args:
            inconsistencies: List of Inconsistency findings to verify.
            suggestions: List of Suggestion findings to verify.
            ir: The Intermediate Representation containing source chunks.

        Returns:
            Tuple of (verified_inconsistencies, verified_suggestions) with
            evidence_verified and all_evidence_unverified flags set.
        """
        # Build lookup structures for efficient verification
        chunk_map: dict[str, str] = {}
        normalized_chunks: list[str] = []

        for chunk in ir.chunks:
            normalized_text = _normalize_whitespace(chunk.text)
            chunk_map[chunk.chunk_id] = normalized_text
            normalized_chunks.append(normalized_text)

        # Verify inconsistencies
        verified_inconsistencies = [
            self._verify_inconsistency(inc, chunk_map, normalized_chunks)
            for inc in inconsistencies
        ]

        # Verify suggestions
        verified_suggestions = [
            self._verify_suggestion(sug, chunk_map, normalized_chunks)
            for sug in suggestions
        ]

        return verified_inconsistencies, verified_suggestions

    def _verify_inconsistency(
        self,
        inconsistency: Inconsistency,
        chunk_map: dict[str, str],
        normalized_chunks: list[str],
    ) -> Inconsistency:
        """Verify all source_refs in an Inconsistency finding."""
        verified_refs = [
            self._verify_source_ref(ref, chunk_map, normalized_chunks)
            for ref in inconsistency.source_refs
        ]

        all_unverified = self._all_evidence_unverified(verified_refs)

        return inconsistency.model_copy(
            update={
                "source_refs": verified_refs,
                "all_evidence_unverified": all_unverified,
            }
        )

    def _verify_suggestion(
        self,
        suggestion: Suggestion,
        chunk_map: dict[str, str],
        normalized_chunks: list[str],
    ) -> Suggestion:
        """Verify all source_refs in a Suggestion finding."""
        verified_refs = [
            self._verify_source_ref(ref, chunk_map, normalized_chunks)
            for ref in suggestion.source_refs
        ]

        all_unverified = self._all_evidence_unverified(verified_refs)

        return suggestion.model_copy(
            update={
                "source_refs": verified_refs,
                "all_evidence_unverified": all_unverified,
            }
        )

    def _verify_source_ref(
        self,
        source_ref: FindingSourceRef,
        chunk_map: dict[str, str],
        normalized_chunks: list[str],
    ) -> FindingSourceRef:
        """Verify a single source_ref's evidence against the IR.

        Algorithm (same as VerificationService):
        1. Normalize whitespace on evidence.
        2. Exact substring match in the referenced chunk_id.
        3. Exact substring match in any IR chunk.
        4. Fuzzy match (80% threshold) in any chunk.
        """
        normalized_evidence = _normalize_whitespace(source_ref.evidence)

        if not normalized_evidence:
            # Empty evidence cannot be verified
            return source_ref.model_copy(update={"evidence_verified": False})

        verified = self._check_evidence(
            normalized_evidence,
            source_ref.chunk_id,
            chunk_map,
            normalized_chunks,
        )

        return source_ref.model_copy(update={"evidence_verified": verified})

    def _check_evidence(
        self,
        normalized_evidence: str,
        referenced_chunk_id: str,
        chunk_map: dict[str, str],
        normalized_chunks: list[str],
    ) -> bool:
        """Check if evidence exists in the IR using the three-step algorithm.

        Steps:
        1. Exact substring match in the referenced chunk_id.
        2. Exact substring match in any IR chunk.
        3. Fuzzy match (80% threshold) in any chunk.
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

    def _all_evidence_unverified(self, source_refs: list[FindingSourceRef]) -> bool:
        """Determine if all source_refs have evidence_verified = False.

        Returns False if the list is empty (no evidence to evaluate).
        """
        if not source_refs:
            return False
        return all(not ref.evidence_verified for ref in source_refs)
