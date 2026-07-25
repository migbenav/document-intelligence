"""Evidence verification service for the Knowledge Model.

Verifies that each knowledge element's source_ref.evidence text span
actually exists in the document's Intermediate Representation (IR).
This is a purely deterministic text-matching operation — no LLM calls (Req 7.5).
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.models.document import ContentChunkModel, IntermediateRepresentation
from app.models.knowledge_model import KnowledgeModel


@dataclass
class VerificationResult:
    """Result of evidence verification across all knowledge elements."""

    verified_count: int
    total_count: int
    verification_rate: float  # 0.0–1.0
    unverified_element_ids: list[str]


def _normalize_whitespace(text: str) -> str:
    """Collapse all whitespace sequences into single spaces and strip."""
    return re.sub(r"\s+", " ", text).strip()


def _fuzzy_match(evidence: str, text: str, threshold: float = 0.8) -> bool:
    """Check if evidence has a fuzzy match within text at or above the threshold.

    Uses SequenceMatcher to find the best matching subsequence in text.
    """
    if not evidence or not text:
        return False
    matcher = SequenceMatcher(None, evidence, text)
    # find_longest_match gives the longest contiguous matching block.
    # ratio() gives overall similarity which works well for substring-like matching.
    # For checking if evidence exists *within* a longer text, we use ratio on
    # sliding windows or simply check ratio against chunks of similar length.
    # A simpler and effective approach: check ratio of evidence against the full text.
    # But this penalizes when text is much longer than evidence.
    # Better: use find_longest_match and compare its size to evidence length.

    # Strategy: find the best matching region in the text of similar length to evidence
    # and check if the similarity ratio exceeds the threshold.
    evidence_len = len(evidence)
    if evidence_len == 0:
        return False

    # For short evidence in long text, sliding window approach
    if len(text) <= evidence_len:
        ratio = SequenceMatcher(None, evidence, text).ratio()
        return ratio >= threshold

    # Check windows of text that are similar length to the evidence
    best_ratio = 0.0
    step = max(1, evidence_len // 4)

    for i in range(0, len(text) - evidence_len + 1, step):
        window = text[i : i + evidence_len]
        ratio = SequenceMatcher(None, evidence, window).ratio()
        if ratio >= threshold:
            return True
        if ratio > best_ratio:
            best_ratio = ratio

    # Also check slightly larger windows to account for length differences
    for i in range(0, max(1, len(text) - evidence_len - step), step):
        window = text[i : i + evidence_len + step]
        ratio = SequenceMatcher(None, evidence, window).ratio()
        if ratio >= threshold:
            return True

    return False


class VerificationService:
    """Verifies evidence references against the source document's IR.

    Verification algorithm (Req 7.2, 7.3):
    1. Normalize whitespace on the evidence text.
    2. Check exact substring match in the referenced chunk_id.
    3. Check exact substring match in any IR chunk.
    4. Check fuzzy match (80% similarity threshold) in any chunk.

    If found at any step, the element is marked verified = True.
    If not found anywhere, the element is marked verified = False.

    This service does NOT call the LLM — purely deterministic (Req 7.5).
    """

    def __init__(self, fuzzy_threshold: float = 0.8):
        self._fuzzy_threshold = fuzzy_threshold

    def verify(
        self, knowledge_model: KnowledgeModel, ir: IntermediateRepresentation
    ) -> VerificationResult:
        """Verify all elements in the Knowledge Model against the IR.

        Args:
            knowledge_model: The Knowledge Model with elements to verify.
            ir: The Intermediate Representation containing source chunks.

        Returns:
            VerificationResult with counts and unverified element IDs.
        """
        # Build a lookup of chunk_id -> normalized text for efficient access
        chunk_map: dict[str, str] = {}
        normalized_chunks: list[str] = []

        for chunk in ir.chunks:
            normalized_text = _normalize_whitespace(chunk.text)
            chunk_map[chunk.chunk_id] = normalized_text
            normalized_chunks.append(normalized_text)

        verified_count = 0
        unverified_element_ids: list[str] = []

        for element in knowledge_model.elements:
            evidence = element.source_ref.evidence
            normalized_evidence = _normalize_whitespace(evidence)

            if not normalized_evidence:
                # Empty evidence cannot be verified
                element.verified = False
                unverified_element_ids.append(element.id)
                continue

            found = self._check_evidence(
                normalized_evidence,
                element.source_ref.chunk_id,
                chunk_map,
                normalized_chunks,
            )

            element.verified = found
            if found:
                verified_count += 1
            else:
                unverified_element_ids.append(element.id)

        total_count = len(knowledge_model.elements)
        verification_rate = verified_count / total_count if total_count > 0 else 0.0

        return VerificationResult(
            verified_count=verified_count,
            total_count=total_count,
            verification_rate=verification_rate,
            unverified_element_ids=unverified_element_ids,
        )

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
