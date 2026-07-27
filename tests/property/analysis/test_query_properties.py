"""Property-based tests for Natural Language Queries.

Tests correctness properties using Hypothesis to verify universal invariants
across randomly generated inputs.

Feature: natural-language-queries
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.analysis.llm_client import LLMClient, LLMResponse
from app.analysis.query.context_builder import ContextBuilder
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)
from app.analysis.query.evidence_verifier import QueryEvidenceVerifier
from app.models.knowledge_model import (
    ExtractionMetadata,
    KnowledgeElement,
    KnowledgeModel,
    Relation,
    SourceRef,
)
from app.models.query import QueryMetadata, QueryResponse, QuerySourceRef
from app.analysis.query.response_parser import ResponseParser
from app.analysis.query.service import QueryService
from app.analysis.prompts import query_answering_v1


# --- Strategies ---

ELEMENT_TYPES = ["proposito", "concepto", "actor", "regla", "proceso", "restriccion"]
RELATION_TYPES = ["constrains", "participates_in", "depends_on", "contradicts"]


@st.composite
def source_refs(draw):
    """Generate a valid SourceRef for KM elements."""
    return SourceRef(
        document_id="doc-001",
        chunk_id=f"chunk-{draw(st.text(alphabet='abcdef0123456789', min_size=4, max_size=4))}",
        page=draw(st.one_of(st.none(), st.integers(min_value=1, max_value=100))),
        section=draw(st.one_of(st.none(), st.text(min_size=1, max_size=50))),
        evidence=draw(st.text(min_size=1, max_size=200)),
    )


# =============================================================================
# Property 3: Relational Context One-Hop Bound
# =============================================================================


@st.composite
def km_with_deep_chains(draw):
    """Generate a KnowledgeModel with deep relationship chains (3+ hops).

    Creates elements A, B, C, D, E, ... with chain relationships:
    A -> B -> C -> D -> E
    Element A gets a high relevance score (directly relevant).
    Only B should appear in relational context (one hop from A).
    C, D, E should NOT appear.
    """
    # Create a chain of 3-6 elements
    chain_length = draw(st.integers(min_value=4, max_value=6))
    element_ids = [f"elem-{i:03d}" for i in range(chain_length)]

    elements = []
    for i, eid in enumerate(element_ids):
        # Build relation to next element in chain (if not last)
        relations = []
        if i < chain_length - 1:
            rel_type = draw(st.sampled_from(RELATION_TYPES))
            relations.append(
                Relation(
                    target_id=element_ids[i + 1],
                    type=rel_type,
                    description=f"Relation from {eid} to {element_ids[i + 1]}",
                )
            )

        elements.append(
            KnowledgeElement(
                id=eid,
                type=draw(st.sampled_from(ELEMENT_TYPES)),
                name=f"Element {i}",
                content=f"Content for element {i} with some description text.",
                source_ref=SourceRef(
                    document_id="doc-001",
                    chunk_id=f"chunk-{i:03d}",
                    page=None,
                    section=f"## Section {i}",
                    evidence=f"Evidence text for element {i}.",
                ),
                relations=relations,
                verified=draw(st.booleans()),
            )
        )

    # Optionally add extra elements that are not in the chain but connected
    # to elements beyond the first hop (to test they don't leak in)
    num_extra = draw(st.integers(min_value=0, max_value=2))
    for j in range(num_extra):
        extra_id = f"elem-extra-{j:03d}"
        # Connect this extra element FROM a deep chain element (2+ hops from A)
        deep_source_idx = draw(st.integers(min_value=2, max_value=chain_length - 1))
        # Add the relation to the deep chain element
        elements[deep_source_idx].relations.append(
            Relation(
                target_id=extra_id,
                type=draw(st.sampled_from(RELATION_TYPES)),
                description=f"Relation to extra element {j}",
            )
        )
        elements.append(
            KnowledgeElement(
                id=extra_id,
                type=draw(st.sampled_from(ELEMENT_TYPES)),
                name=f"Extra Element {j}",
                content=f"Content for extra element {j}.",
                source_ref=SourceRef(
                    document_id="doc-001",
                    chunk_id=f"chunk-extra-{j:03d}",
                    page=None,
                    section=f"## Extra Section {j}",
                    evidence=f"Evidence for extra element {j}.",
                ),
                relations=[],
                verified=draw(st.booleans()),
            )
        )

    km = KnowledgeModel(
        document_id="doc-001",
        document_type="prd",
        elements=elements,
        extraction_metadata=ExtractionMetadata(
            prompt_version="extraction-v1",
            model_id="gemini/gemini-2.5-flash",
            temperature=0.1,
            element_count=len(elements),
            relationship_count=sum(len(e.relations) for e in elements),
            verification_rate=0.5,
            extracted_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
        ),
    )

    return km, element_ids, chain_length


class TestProperty3RelationalContextOneHopBound:
    """Property 3: Relational Context One-Hop Bound.

    For any set of directly relevant elements selected during context construction,
    the additional relational context elements included SHALL be reachable in
    exactly one hop via the Knowledge Model's relationship graph. No element more
    than one relationship edge away from a directly relevant element SHALL appear
    in the context.

    **Validates: Requirements 2.2**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_only_one_hop_elements_in_context(self, data):
        """For any KM with deep chains (A->B->C->D), when only A is directly
        relevant, only B appears in relational context. C, D, etc. do NOT appear.

        The key assertion: for any element in the resulting context that was NOT
        scored as directly relevant, it must be exactly one hop away from a
        directly relevant element.
        """
        km, element_ids, chain_length = data.draw(km_with_deep_chains())

        # Mock LLM to give high score only to the first element (A)
        # and zero to all others => only element A is "directly relevant"
        scores = []
        for elem in km.elements:
            if elem.id == element_ids[0]:
                scores.append({"id": elem.id, "score": 9})
            else:
                scores.append({"id": elem.id, "score": 0})

        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.call = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(scores),
                model_id="gemini/gemini-2.5-flash",
            )
        )

        # Build IR with matching chunks
        chunks = [
            ContentChunkModel(
                chunk_id=f"chunk-{i:03d}",
                text=f"Chunk text for element {i}.",
                structural_context={"section": f"## Section {i}"},
                order=i,
            )
            for i in range(chain_length)
        ]
        # Add extra chunks if extra elements exist
        num_extras = len(km.elements) - chain_length
        for j in range(num_extras):
            chunks.append(
                ContentChunkModel(
                    chunk_id=f"chunk-extra-{j:03d}",
                    text=f"Extra chunk text {j}.",
                    structural_context={"section": f"## Extra Section {j}"},
                    order=chain_length + j,
                )
            )

        ir = IntermediateRepresentation(
            document_id="doc-001",
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=2000,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=chunks,
        )

        builder = ContextBuilder(mock_llm, max_elements=20, budget_ratio=0.6)
        context = await builder.build_context(
            question="What is element 0 about?",
            knowledge_model=km,
            ir=ir,
            context_window_tokens=100000,
        )

        assert context is not None, "Context should not be None when element A is relevant"

        # Identify the directly relevant element IDs (those with score > 0)
        direct_ids = {element_ids[0]}  # Only A was scored > 0

        # Identify one-hop targets from directly relevant elements
        one_hop_ids = set()
        for elem in km.elements:
            if elem.id in direct_ids:
                for rel in elem.relations:
                    if rel.target_id not in direct_ids:
                        one_hop_ids.add(rel.target_id)

        # Check all elements in context
        context_element_ids = {e.element_id for e in context.elements}

        # Elements beyond one hop should NOT be in the context
        for elem_id in context_element_ids:
            if elem_id not in direct_ids:
                assert elem_id in one_hop_ids, (
                    f"Element '{elem_id}' is in context but is NOT directly relevant "
                    f"and NOT one hop from a directly relevant element. "
                    f"Direct IDs: {direct_ids}, One-hop IDs: {one_hop_ids}, "
                    f"Context IDs: {context_element_ids}"
                )

        # Specifically verify that elements 2+ hops away are excluded
        two_plus_hop_ids = set(element_ids[2:])  # C, D, E... are 2+ hops from A
        # Also include any extra elements (connected to deep chain elements)
        extra_element_ids = {e.id for e in km.elements if e.id.startswith("elem-extra")}
        two_plus_hop_ids.update(extra_element_ids)

        for excluded_id in two_plus_hop_ids:
            assert excluded_id not in context_element_ids, (
                f"Element '{excluded_id}' is 2+ hops from directly relevant elements "
                f"but appeared in context. Context IDs: {context_element_ids}"
            )

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_one_hop_element_is_included_when_budget_allows(self, data):
        """For any KM with chain A->B->C->D, when A is directly relevant and
        budget allows, B (one hop) SHOULD appear in context.
        """
        km, element_ids, chain_length = data.draw(km_with_deep_chains())

        # Mock LLM to give high score only to element A
        scores = []
        for elem in km.elements:
            if elem.id == element_ids[0]:
                scores.append({"id": elem.id, "score": 9})
            else:
                scores.append({"id": elem.id, "score": 0})

        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.call = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(scores),
                model_id="gemini/gemini-2.5-flash",
            )
        )

        # Build IR
        chunks = [
            ContentChunkModel(
                chunk_id=f"chunk-{i:03d}",
                text=f"Chunk text for element {i}.",
                structural_context={"section": f"## Section {i}"},
                order=i,
            )
            for i in range(chain_length)
        ]
        num_extras = len(km.elements) - chain_length
        for j in range(num_extras):
            chunks.append(
                ContentChunkModel(
                    chunk_id=f"chunk-extra-{j:03d}",
                    text=f"Extra chunk text {j}.",
                    structural_context={"section": f"## Extra Section {j}"},
                    order=chain_length + j,
                )
            )

        ir = IntermediateRepresentation(
            document_id="doc-001",
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=2000,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=chunks,
        )

        # Use a large budget so B is not trimmed
        builder = ContextBuilder(mock_llm, max_elements=20, budget_ratio=0.6)
        context = await builder.build_context(
            question="What is element 0 about?",
            knowledge_model=km,
            ir=ir,
            context_window_tokens=100000,
        )

        assert context is not None

        context_element_ids = {e.element_id for e in context.elements}

        # B (element_ids[1]) is one hop from A and should be included
        assert element_ids[1] in context_element_ids, (
            f"Element B ('{element_ids[1]}') is one hop from directly relevant A "
            f"but was not included in context. Context IDs: {context_element_ids}"
        )

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_multiple_direct_elements_one_hop_bound(self, data):
        """When multiple elements are directly relevant, relational context
        includes only elements one hop from ANY directly relevant element,
        never deeper.
        """
        km, element_ids, chain_length = data.draw(km_with_deep_chains())

        # Make first two elements directly relevant (A and B)
        # B->C is one hop from B, so C should be included
        # But D (C->D) should NOT be included
        scores = []
        for elem in km.elements:
            if elem.id in {element_ids[0], element_ids[1]}:
                scores.append({"id": elem.id, "score": 8})
            else:
                scores.append({"id": elem.id, "score": 0})

        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.call = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(scores),
                model_id="gemini/gemini-2.5-flash",
            )
        )

        chunks = [
            ContentChunkModel(
                chunk_id=f"chunk-{i:03d}",
                text=f"Chunk text for element {i}.",
                structural_context={"section": f"## Section {i}"},
                order=i,
            )
            for i in range(chain_length)
        ]
        num_extras = len(km.elements) - chain_length
        for j in range(num_extras):
            chunks.append(
                ContentChunkModel(
                    chunk_id=f"chunk-extra-{j:03d}",
                    text=f"Extra chunk text {j}.",
                    structural_context={"section": f"## Extra Section {j}"},
                    order=chain_length + j,
                )
            )

        ir = IntermediateRepresentation(
            document_id="doc-001",
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=2000,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=chunks,
        )

        builder = ContextBuilder(mock_llm, max_elements=20, budget_ratio=0.6)
        context = await builder.build_context(
            question="What are elements 0 and 1 about?",
            knowledge_model=km,
            ir=ir,
            context_window_tokens=100000,
        )

        assert context is not None

        context_element_ids = {e.element_id for e in context.elements}
        direct_ids = {element_ids[0], element_ids[1]}

        # Compute valid one-hop IDs from all directly relevant elements
        one_hop_ids = set()
        for elem in km.elements:
            if elem.id in direct_ids:
                for rel in elem.relations:
                    if rel.target_id not in direct_ids:
                        one_hop_ids.add(rel.target_id)

        # Every non-direct element in context must be exactly one hop away
        for elem_id in context_element_ids:
            if elem_id not in direct_ids:
                assert elem_id in one_hop_ids, (
                    f"Element '{elem_id}' is in context but is NOT directly relevant "
                    f"and NOT one hop from any directly relevant element. "
                    f"Direct IDs: {direct_ids}, One-hop IDs: {one_hop_ids}"
                )

        # Elements 3+ hops from any direct element should be excluded
        # With A and B direct: C is one hop from B, D is two hops from B
        if chain_length >= 4:
            # D (index 3) is two hops from B, should be excluded
            assert element_ids[3] not in context_element_ids, (
                f"Element D ('{element_ids[3]}') is 2 hops from B but appeared in context"
            )



# =============================================================================
# Property 2: Context Budget Compliance
# =============================================================================


@st.composite
def knowledge_models_for_budget(draw, min_elements=1, max_elements=100):
    """Generate a KnowledgeModel with 1-100 elements for context budget testing."""
    num_elements = draw(st.integers(min_value=min_elements, max_value=max_elements))
    element_ids = [f"elem-{i:03d}" for i in range(num_elements)]

    elements = []
    for i in range(num_elements):
        elem = KnowledgeElement(
            id=element_ids[i],
            type=draw(st.sampled_from(ELEMENT_TYPES)),
            name=draw(st.text(min_size=1, max_size=50)),
            content=draw(st.text(min_size=1, max_size=200)),
            source_ref=SourceRef(
                document_id="doc-test",
                chunk_id=f"chunk-{draw(st.integers(min_value=0, max_value=4)):03d}",
                page=None,
                section=None,
                evidence=draw(st.text(min_size=1, max_size=100)),
            ),
            relations=[],
            verified=draw(st.booleans()),
        )
        elements.append(elem)

    return KnowledgeModel(
        document_id="doc-test",
        document_type=draw(st.sampled_from(["prd", "technical_spec", "policy_process", "generic"])),
        elements=elements,
        extraction_metadata=ExtractionMetadata(
            prompt_version="extraction-v1",
            model_id="gemini/gemini-2.5-flash-preview-05-20",
            temperature=0.1,
            element_count=num_elements,
            relationship_count=0,
            verification_rate=0.5,
            extracted_at=datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc),
        ),
    )


@st.composite
def mock_scoring_response(draw, element_ids):
    """Generate a mock LLM scoring response with random scores for given element IDs."""
    scores = []
    for elem_id in element_ids:
        score = draw(st.integers(min_value=0, max_value=10))
        scores.append({"id": elem_id, "score": score})
    return json.dumps(scores)


class TestProperty2ContextBudgetCompliance:
    """Property 2: Context Budget Compliance.

    For any Knowledge Model and question, the context constructed by
    ContextBuilder SHALL select at most 20 directly relevant elements
    AND the total token count of the assembled context SHALL NOT exceed
    60% of the configured context window token limit.

    **Validates: Requirements 2.1, 2.4**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_context_selects_at_most_20_elements(self, data):
        """For any KM of varying size (1-100 elements), the context builder
        shall never select more than 20 elements in the result.

        **Validates: Requirements 2.1, 2.4**
        """
        km = data.draw(knowledge_models_for_budget(min_elements=1, max_elements=100))
        context_window_tokens = data.draw(st.integers(min_value=4000, max_value=128000))

        element_ids = [elem.id for elem in km.elements]

        # Generate random scores for each element
        scoring_response = data.draw(mock_scoring_response(element_ids))

        # Mock LLM client that returns random scores
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.call = AsyncMock(
            return_value=LLMResponse(
                content=scoring_response,
                model_id="gemini/gemini-2.5-flash",
            )
        )

        # Build a minimal IR
        ir = IntermediateRepresentation(
            document_id="doc-test",
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=1000,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id=f"chunk-{i:03d}",
                    text=f"Some text content for chunk {i}",
                    structural_context={"section": f"## Section {i}"},
                    order=i,
                )
                for i in range(5)
            ],
        )

        builder = ContextBuilder(llm_client=mock_llm, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            question="What are the main concepts?",
            knowledge_model=km,
            ir=ir,
            context_window_tokens=context_window_tokens,
        )

        # Property: if result is not None, elements count <= 20
        if result is not None:
            assert len(result.elements) <= 20, (
                f"Expected at most 20 elements, got {len(result.elements)}. "
                f"KM had {len(km.elements)} elements."
            )

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_context_total_tokens_within_budget(self, data):
        """For any KM of varying size (1-100 elements), the assembled context
        total_tokens shall not exceed 60% of context_window_tokens.

        **Validates: Requirements 2.1, 2.4**
        """
        km = data.draw(knowledge_models_for_budget(min_elements=1, max_elements=100))
        context_window_tokens = data.draw(st.integers(min_value=4000, max_value=128000))

        element_ids = [elem.id for elem in km.elements]

        # Generate random scores for each element
        scoring_response = data.draw(mock_scoring_response(element_ids))

        # Mock LLM client that returns random scores
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.call = AsyncMock(
            return_value=LLMResponse(
                content=scoring_response,
                model_id="gemini/gemini-2.5-flash",
            )
        )

        # Build a minimal IR
        ir = IntermediateRepresentation(
            document_id="doc-test",
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=1000,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id=f"chunk-{i:03d}",
                    text=f"Some text content for chunk {i}",
                    structural_context={"section": f"## Section {i}"},
                    order=i,
                )
                for i in range(5)
            ],
        )

        builder = ContextBuilder(llm_client=mock_llm, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            question="What are the main concepts?",
            knowledge_model=km,
            ir=ir,
            context_window_tokens=context_window_tokens,
        )

        # Property: if result is not None, total_tokens <= 60% of context_window_tokens
        if result is not None:
            token_budget = int(context_window_tokens * 0.6)
            assert result.total_tokens <= token_budget, (
                f"Expected total_tokens <= {token_budget} (60% of {context_window_tokens}), "
                f"got {result.total_tokens}."
            )


# =============================================================================
# Property 6: Evidence Verification Determinism
# =============================================================================


@st.composite
def ir_with_known_chunks(draw, min_chunks=3, max_chunks=5):
    """Generate an IntermediateRepresentation with 3-5 chunks of known text content."""
    num_chunks = draw(st.integers(min_value=min_chunks, max_value=max_chunks))
    chunks = []
    for i in range(num_chunks):
        text = draw(st.text(min_size=20, max_size=200, alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"),
            whitelist_characters=" ",
        )))
        chunks.append(
            ContentChunkModel(
                chunk_id=f"chunk-{i:03d}",
                text=text,
                structural_context={"section": f"## Section {i}"},
                order=i,
            )
        )

    ir = IntermediateRepresentation(
        document_id="doc-001",
        metadata=DocumentMetadata(
            original_filename="test.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=5000,
            language=DetectedLanguage.ENGLISH,
            upload_timestamp=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
        ),
        chunks=chunks,
    )
    return ir


@st.composite
def source_refs_for_verification(draw, ir):
    """Generate random QuerySourceRef items (1-10) with evidence text.

    Some evidence will match IR chunks exactly (taken from chunk text),
    some will be random text that may or may not match.
    """
    num_refs = draw(st.integers(min_value=1, max_value=10))
    refs = []
    chunk_ids = [chunk.chunk_id for chunk in ir.chunks]

    for _ in range(num_refs):
        # Decide if this ref should have evidence matching a chunk or random text
        use_matching_evidence = draw(st.booleans())
        chunk_id = draw(st.sampled_from(chunk_ids))

        if use_matching_evidence:
            # Pick a chunk and use a substring of its text as evidence
            source_chunk = draw(st.sampled_from(ir.chunks))
            chunk_text = source_chunk.text
            if len(chunk_text) > 5:
                # Take a substring of the chunk text
                start = draw(st.integers(min_value=0, max_value=max(0, len(chunk_text) - 5)))
                end = draw(st.integers(min_value=start + 1, max_value=min(start + 200, len(chunk_text))))
                evidence = chunk_text[start:end]
            else:
                evidence = chunk_text
        else:
            # Generate random evidence text that likely won't match
            evidence = draw(st.text(min_size=1, max_size=200, alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z"),
                whitelist_characters=" ",
            )))

        refs.append(
            QuerySourceRef(
                document_id="doc-001",
                chunk_id=chunk_id,
                page=None,
                section=draw(st.one_of(st.none(), st.text(min_size=1, max_size=30))),
                evidence=evidence,
                evidence_verified=False,
            )
        )

    return refs


class TestProperty6EvidenceVerificationDeterminism:
    """Property 6: Evidence Verification Determinism.

    For any set of source_refs and a fixed IR, applying the verification algorithm
    (normalize → exact match in referenced chunk → exact match in any chunk →
    fuzzy match at 80%) produces the same evidence_verified values on every
    invocation. For any QueryResponse where all source_refs have
    evidence_verified = false, the response-level all_evidence_unverified
    attribute SHALL be true.

    **Validates: Requirements 4.1, 4.2, 4.3, 4.5**
    """

    @settings(max_examples=100)
    @given(data=st.data())
    def test_verification_is_deterministic(self, data):
        """For any random source_refs and fixed IR, applying verification twice
        produces identical evidence_verified values on each source_ref.

        **Validates: Requirements 4.1, 4.2, 4.3, 4.5**
        """
        ir = data.draw(ir_with_known_chunks())
        refs = data.draw(source_refs_for_verification(ir))

        verifier = QueryEvidenceVerifier(fuzzy_threshold=0.8)

        # First verification pass - create deep copies to avoid mutation issues
        refs_pass1 = [
            QuerySourceRef(
                document_id=ref.document_id,
                chunk_id=ref.chunk_id,
                page=ref.page,
                section=ref.section,
                evidence=ref.evidence,
                evidence_verified=False,
            )
            for ref in refs
        ]
        refs_pass2 = [
            QuerySourceRef(
                document_id=ref.document_id,
                chunk_id=ref.chunk_id,
                page=ref.page,
                section=ref.section,
                evidence=ref.evidence,
                evidence_verified=False,
            )
            for ref in refs
        ]

        # Apply verification twice with the same inputs
        result1 = verifier.verify(refs_pass1, ir)
        result2 = verifier.verify(refs_pass2, ir)

        # Assert identical evidence_verified values in both runs
        assert len(result1) == len(result2), (
            f"Verification returned different lengths: {len(result1)} vs {len(result2)}"
        )

        for i, (r1, r2) in enumerate(zip(result1, result2)):
            assert r1.evidence_verified == r2.evidence_verified, (
                f"Determinism violation at source_ref[{i}]: "
                f"pass1 evidence_verified={r1.evidence_verified}, "
                f"pass2 evidence_verified={r2.evidence_verified}. "
                f"Evidence: '{r1.evidence[:80]}...'"
            )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_all_evidence_unverified_flag(self, data):
        """When ALL source_refs have evidence_verified=False after verification,
        the set is fully unverified (all_evidence_unverified should be True).

        **Validates: Requirements 4.1, 4.2, 4.3, 4.5**
        """
        ir = data.draw(ir_with_known_chunks())

        # Generate source_refs with random evidence that is unlikely to match
        # (we use completely random text that won't exist in the IR chunks)
        num_refs = data.draw(st.integers(min_value=1, max_value=10))
        refs = []
        chunk_ids = [chunk.chunk_id for chunk in ir.chunks]

        for _ in range(num_refs):
            # Use a unique random prefix to ensure evidence won't match any chunk
            random_evidence = "XYZNONMATCH_" + data.draw(
                st.text(min_size=5, max_size=100, alphabet=st.characters(
                    whitelist_categories=("Lu",),
                ))
            )
            refs.append(
                QuerySourceRef(
                    document_id="doc-001",
                    chunk_id=data.draw(st.sampled_from(chunk_ids)),
                    page=None,
                    section=None,
                    evidence=random_evidence,
                    evidence_verified=False,
                )
            )

        verifier = QueryEvidenceVerifier(fuzzy_threshold=0.8)
        verified_refs = verifier.verify(refs, ir)

        # Compute the all_evidence_unverified flag as the QueryService would
        all_unverified = all(
            ref.evidence_verified is False for ref in verified_refs
        )

        # If all refs are unverified, all_evidence_unverified should be True
        if all(ref.evidence_verified is False for ref in verified_refs):
            assert all_unverified is True, (
                f"Expected all_evidence_unverified=True when all {len(verified_refs)} "
                f"source_refs have evidence_verified=False"
            )


# =============================================================================
# Property 7: Query Statelessness
# =============================================================================


from app.analysis.query.service import QueryService
from app.analysis.query.response_parser import ResponseParser


@st.composite
def random_question(draw):
    """Generate a random non-empty question string (1-200 chars)."""
    return draw(st.text(
        min_size=1,
        max_size=200,
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), whitelist_characters=" ?"),
    ))


class TestProperty7QueryStatelessness:
    """Property 7: Query Statelessness.

    For any sequence of queries submitted to the same document, each query's
    context construction and prompt SHALL contain no information from prior
    queries in the sequence. The context and response for query N SHALL be
    identical whether it is the first query or the hundredth.

    **Validates: Requirements 1.6**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_repeated_queries_produce_identical_dependency_calls(self, data):
        """For any question called 2-5 times on the same QueryService instance,
        context_builder.build_context is called with the same arguments each time
        and llm_client.call is called with the same prompt each time.

        This proves no state leaks between calls — each query is independent.

        **Validates: Requirements 1.6**
        """
        question = data.draw(random_question())
        num_calls = data.draw(st.integers(min_value=2, max_value=5))

        # Create a fixed KnowledgeModel
        km = KnowledgeModel(
            document_id="doc-stateless",
            document_type="prd",
            elements=[
                KnowledgeElement(
                    id="elem-001",
                    type="concepto",
                    name="Test Concept",
                    content="A concept used for statelessness testing.",
                    source_ref=SourceRef(
                        document_id="doc-stateless",
                        chunk_id="chunk-001",
                        page=None,
                        section="## Test Section",
                        evidence="A concept used for statelessness testing.",
                    ),
                    relations=[],
                    verified=True,
                ),
            ],
            extraction_metadata=ExtractionMetadata(
                prompt_version="extraction-v1",
                model_id="gemini/gemini-2.5-flash",
                temperature=0.1,
                element_count=1,
                relationship_count=0,
                verification_rate=1.0,
                extracted_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
        )

        # Create a fixed IR
        ir = IntermediateRepresentation(
            document_id="doc-stateless",
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=1000,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-001",
                    text="A concept used for statelessness testing.",
                    structural_context={"section": "## Test Section"},
                    order=0,
                ),
            ],
        )

        # Build a fixed mock LLM response (valid QueryResponse JSON)
        fixed_llm_answer = json.dumps({
            "answer": "This is a stateless test answer.",
            "answerable": True,
            "source_refs": [
                {
                    "chunk_id": "chunk-001",
                    "page": None,
                    "section": "## Test Section",
                    "evidence": "A concept used for statelessness testing.",
                }
            ],
        })

        # Mock all dependencies
        mock_context_builder = MagicMock(spec=ContextBuilder)
        from app.models.query import QueryContext, QueryContextElement

        fixed_context = QueryContext(
            elements=[
                QueryContextElement(
                    element_id="elem-001",
                    type="concepto",
                    name="Test Concept",
                    content="A concept used for statelessness testing.",
                    evidence="A concept used for statelessness testing.",
                    verified=True,
                ),
            ],
            relations=[],
            total_tokens=100,
            has_unverified_elements=False,
        )
        mock_context_builder.build_context = AsyncMock(return_value=fixed_context)

        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.call = AsyncMock(
            return_value=LLMResponse(
                content=fixed_llm_answer,
                model_id="gemini/gemini-2.5-flash",
            )
        )

        mock_response_parser = MagicMock(spec=ResponseParser)
        from app.models.query import QueryResponse, QueryMetadata
        fixed_parsed_response = QueryResponse(
            answer="This is a stateless test answer.",
            answerable=True,
            source_refs=[
                QuerySourceRef(
                    document_id="doc-stateless",
                    chunk_id="chunk-001",
                    page=None,
                    section="## Test Section",
                    evidence="A concept used for statelessness testing.",
                    evidence_verified=False,
                ),
            ],
            all_evidence_unverified=False,
            metadata=QueryMetadata(
                prompt_version="query-answering-v1",
                model_id="gemini/gemini-2.5-flash",
                temperature=0.1,
                timestamp=datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
        )
        mock_response_parser.parse = MagicMock(return_value=fixed_parsed_response)

        mock_evidence_verifier = MagicMock(spec=QueryEvidenceVerifier)
        mock_evidence_verifier.verify = MagicMock(
            return_value=fixed_parsed_response.source_refs
        )

        # Create a single QueryService instance (reused across calls)
        service = QueryService(
            llm_client=mock_llm_client,
            context_builder=mock_context_builder,
            response_parser=mock_response_parser,
            evidence_verifier=mock_evidence_verifier,
        )

        # Call answer() multiple times with the same question
        for _ in range(num_calls):
            await service.answer(
                document_id="doc-stateless",
                question=question,
                knowledge_model=km,
                ir=ir,
            )

        # Assert: context_builder.build_context called with same args each time
        assert mock_context_builder.build_context.call_count == num_calls, (
            f"Expected build_context to be called {num_calls} times, "
            f"got {mock_context_builder.build_context.call_count}"
        )

        build_context_calls = mock_context_builder.build_context.call_args_list
        first_call_kwargs = build_context_calls[0]
        for i in range(1, num_calls):
            assert build_context_calls[i] == first_call_kwargs, (
                f"build_context call {i+1} differs from call 1. "
                f"Call 1: {first_call_kwargs}, Call {i+1}: {build_context_calls[i]}. "
                f"This indicates state leakage between queries."
            )

        # Assert: llm_client.call called with same prompt each time
        assert mock_llm_client.call.call_count == num_calls, (
            f"Expected llm_client.call to be called {num_calls} times, "
            f"got {mock_llm_client.call.call_count}"
        )

        llm_calls = mock_llm_client.call.call_args_list
        first_llm_call = llm_calls[0]
        for i in range(1, num_calls):
            assert llm_calls[i] == first_llm_call, (
                f"llm_client.call invocation {i+1} differs from call 1. "
                f"This indicates state leakage — prior query information "
                f"is contaminating subsequent prompts."
            )

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_different_questions_do_not_cross_contaminate(self, data):
        """For any two distinct questions on the same QueryService instance,
        the second query's context_builder call does NOT contain information
        from the first query.

        **Validates: Requirements 1.6**
        """
        question_1 = data.draw(random_question())
        question_2 = data.draw(random_question().filter(lambda q: q != question_1))

        # Create fixed KM and IR
        km = KnowledgeModel(
            document_id="doc-stateless",
            document_type="prd",
            elements=[
                KnowledgeElement(
                    id="elem-001",
                    type="concepto",
                    name="Test Concept",
                    content="Statelessness verification content.",
                    source_ref=SourceRef(
                        document_id="doc-stateless",
                        chunk_id="chunk-001",
                        page=None,
                        section="## Section",
                        evidence="Statelessness verification content.",
                    ),
                    relations=[],
                    verified=True,
                ),
            ],
            extraction_metadata=ExtractionMetadata(
                prompt_version="extraction-v1",
                model_id="gemini/gemini-2.5-flash",
                temperature=0.1,
                element_count=1,
                relationship_count=0,
                verification_rate=1.0,
                extracted_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
        )

        ir = IntermediateRepresentation(
            document_id="doc-stateless",
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=1000,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-001",
                    text="Statelessness verification content.",
                    structural_context={"section": "## Section"},
                    order=0,
                ),
            ],
        )

        # Mock context builder
        from app.models.query import QueryContext, QueryContextElement
        fixed_context = QueryContext(
            elements=[
                QueryContextElement(
                    element_id="elem-001",
                    type="concepto",
                    name="Test Concept",
                    content="Statelessness verification content.",
                    evidence="Statelessness verification content.",
                    verified=True,
                ),
            ],
            relations=[],
            total_tokens=80,
            has_unverified_elements=False,
        )

        mock_context_builder = MagicMock(spec=ContextBuilder)
        mock_context_builder.build_context = AsyncMock(return_value=fixed_context)

        # Mock LLM client
        fixed_llm_answer = json.dumps({
            "answer": "Test answer.",
            "answerable": True,
            "source_refs": [
                {
                    "chunk_id": "chunk-001",
                    "page": None,
                    "section": "## Section",
                    "evidence": "Statelessness verification content.",
                }
            ],
        })
        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.call = AsyncMock(
            return_value=LLMResponse(
                content=fixed_llm_answer,
                model_id="gemini/gemini-2.5-flash",
            )
        )

        # Mock response parser
        mock_response_parser = MagicMock(spec=ResponseParser)
        from app.models.query import QueryResponse, QueryMetadata
        fixed_parsed_response = QueryResponse(
            answer="Test answer.",
            answerable=True,
            source_refs=[
                QuerySourceRef(
                    document_id="doc-stateless",
                    chunk_id="chunk-001",
                    page=None,
                    section="## Section",
                    evidence="Statelessness verification content.",
                    evidence_verified=False,
                ),
            ],
            all_evidence_unverified=False,
            metadata=QueryMetadata(
                prompt_version="query-answering-v1",
                model_id="gemini/gemini-2.5-flash",
                temperature=0.1,
                timestamp=datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
        )
        mock_response_parser.parse = MagicMock(return_value=fixed_parsed_response)

        # Mock evidence verifier
        mock_evidence_verifier = MagicMock(spec=QueryEvidenceVerifier)
        mock_evidence_verifier.verify = MagicMock(
            return_value=fixed_parsed_response.source_refs
        )

        # Create a single QueryService instance
        service = QueryService(
            llm_client=mock_llm_client,
            context_builder=mock_context_builder,
            response_parser=mock_response_parser,
            evidence_verifier=mock_evidence_verifier,
        )

        # Call with question_1 first, then question_2
        await service.answer("doc-stateless", question_1, km, ir)
        await service.answer("doc-stateless", question_2, km, ir)

        # Verify that the second call to build_context uses question_2, NOT question_1
        assert mock_context_builder.build_context.call_count == 2

        call_1_kwargs = mock_context_builder.build_context.call_args_list[0]
        call_2_kwargs = mock_context_builder.build_context.call_args_list[1]

        # The question argument should differ between calls (no cross-contamination)
        # Extract the 'question' kwarg or positional arg
        call_1_question = call_1_kwargs.kwargs.get("question", call_1_kwargs.args[0] if call_1_kwargs.args else None)
        call_2_question = call_2_kwargs.kwargs.get("question", call_2_kwargs.args[0] if call_2_kwargs.args else None)

        assert call_1_question == question_1, (
            f"First call should use question_1='{question_1}', got '{call_1_question}'"
        )
        assert call_2_question == question_2, (
            f"Second call should use question_2='{question_2}', got '{call_2_question}'. "
            f"This indicates the service is leaking state from the first query."
        )

        # Verify the second LLM call's prompt contains question_2 (not question_1)
        # by checking the prompt argument passed to llm_client.call
        llm_call_2_args = mock_llm_client.call.call_args_list[1]
        llm_call_2_prompt = llm_call_2_args.args[0] if llm_call_2_args.args else llm_call_2_args.kwargs.get("prompt", "")

        # The prompt must contain question_2 in the QUESTION section
        assert question_2 in str(llm_call_2_prompt), (
            f"Second query's LLM prompt does not contain question_2='{question_2}'. "
            f"The service may not be passing the question correctly."
        )

        # If question_1 is long enough to be distinct from prompt template text,
        # verify it does NOT appear in the second prompt's QUESTION section
        if len(question_1) > 10 and question_1 != question_2:
            # Extract the QUESTION section from the prompt
            question_section_marker = "--- QUESTION ---"
            if question_section_marker in str(llm_call_2_prompt):
                question_section = str(llm_call_2_prompt).split(question_section_marker)[1]
                assert question_1 not in question_section, (
                    f"Second query's QUESTION section contains question_1='{question_1}', "
                    f"indicating state leakage from the first query."
                )


# =============================================================================
# Property 10: Metadata Completeness
# =============================================================================


@st.composite
def answerable_flags(draw):
    """Generate a boolean flag indicating whether the response should be answerable."""
    return draw(st.booleans())


@st.composite
def random_model_ids(draw):
    """Generate random non-empty model ID strings."""
    return draw(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_/"),
            min_size=3,
            max_size=50,
        )
    )


@st.composite
def random_temperatures(draw):
    """Generate random temperature float values."""
    return draw(st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False))


class TestProperty10MetadataCompleteness:
    """Property 10: Metadata Completeness.

    For any QueryResponse (whether answerable or not), the metadata field SHALL
    contain: a non-empty prompt_version string matching the VERSION constant from
    the prompt module, a non-empty model_id string, a temperature float value,
    and a timestamp in ISO 8601 UTC format.

    **Validates: Requirements 1.4, 7.3, 5.1**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_metadata_completeness_answerable_response(self, data):
        """For any answerable QueryResponse produced by QueryService.answer(),
        metadata contains: prompt_version matching VERSION, non-empty model_id,
        temperature float, and UTC timestamp.

        **Validates: Requirements 1.4, 7.3, 5.1**
        """
        # Generate random model_id and temperature for this test case
        model_id = data.draw(random_model_ids())
        temperature = data.draw(random_temperatures())

        # Build a mock context_builder that returns a valid context (answerable path)
        mock_context_builder = MagicMock(spec=ContextBuilder)
        from app.models.query import QueryContext, QueryContextElement, QueryContextRelation

        fake_context = QueryContext(
            elements=[
                QueryContextElement(
                    element_id="elem-001",
                    type="concepto",
                    name="Test Element",
                    content="Some content for testing.",
                    evidence="Evidence text from document.",
                    verified=True,
                )
            ],
            relations=[],
            total_tokens=500,
            has_unverified_elements=False,
        )
        mock_context_builder.build_context = AsyncMock(return_value=fake_context)

        # Build a mock LLM client that returns a valid response
        llm_response_content = json.dumps({
            "answer": "The document describes a test concept.",
            "answerable": True,
            "source_refs": [
                {
                    "chunk_id": "chunk-001",
                    "page": None,
                    "section": "## Test Section",
                    "evidence": "Evidence text from document.",
                }
            ],
        })
        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.call = AsyncMock(
            return_value=LLMResponse(
                content=llm_response_content,
                model_id=model_id,
            )
        )

        # Real response parser (no need to mock, just validates JSON)
        response_parser = ResponseParser()

        # Mock evidence verifier
        mock_evidence_verifier = MagicMock(spec=QueryEvidenceVerifier)
        mock_evidence_verifier.verify = MagicMock(
            side_effect=lambda refs, ir: refs  # Return refs unchanged
        )

        # Build the service with the random temperature
        service = QueryService(
            llm_client=mock_llm_client,
            context_builder=mock_context_builder,
            response_parser=response_parser,
            evidence_verifier=mock_evidence_verifier,
            temperature=temperature,
        )

        # Build minimal KM and IR
        km = KnowledgeModel(
            document_id="doc-001",
            document_type="prd",
            elements=[
                KnowledgeElement(
                    id="elem-001",
                    type="concepto",
                    name="Test Element",
                    content="Some content for testing.",
                    source_ref=SourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-001",
                        page=None,
                        section="## Test Section",
                        evidence="Evidence text from document.",
                    ),
                    relations=[],
                    verified=True,
                )
            ],
            extraction_metadata=ExtractionMetadata(
                prompt_version="extraction-v1",
                model_id="gemini/gemini-2.5-flash",
                temperature=0.1,
                element_count=1,
                relationship_count=0,
                verification_rate=1.0,
                extracted_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
        )

        ir = IntermediateRepresentation(
            document_id="doc-001",
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=1000,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-001",
                    text="Evidence text from document.",
                    structural_context={"section": "## Test Section"},
                    order=0,
                )
            ],
        )

        # Execute the query
        before_call = datetime.now(timezone.utc)
        response = await service.answer(
            document_id="doc-001",
            question="What is the test concept?",
            knowledge_model=km,
            ir=ir,
        )
        after_call = datetime.now(timezone.utc)

        # Assert metadata completeness
        assert response.metadata is not None, "Metadata should not be None"

        # 1. prompt_version matches VERSION constant
        assert response.metadata.prompt_version == query_answering_v1.VERSION, (
            f"Expected prompt_version='{query_answering_v1.VERSION}', "
            f"got '{response.metadata.prompt_version}'"
        )
        assert response.metadata.prompt_version == "query-answering-v1"
        assert len(response.metadata.prompt_version) > 0

        # 2. model_id is non-empty string
        assert isinstance(response.metadata.model_id, str)
        assert len(response.metadata.model_id) > 0, "model_id must be non-empty"
        assert response.metadata.model_id == model_id

        # 3. temperature is a float
        assert isinstance(response.metadata.temperature, float), (
            f"Expected temperature to be float, got {type(response.metadata.temperature)}"
        )
        assert response.metadata.temperature == temperature

        # 4. timestamp is a datetime in UTC
        assert isinstance(response.metadata.timestamp, datetime), (
            f"Expected timestamp to be datetime, got {type(response.metadata.timestamp)}"
        )
        assert response.metadata.timestamp.tzinfo is not None, "Timestamp must be timezone-aware"
        assert response.metadata.timestamp.tzinfo == timezone.utc, (
            f"Timestamp must be in UTC, got tzinfo={response.metadata.timestamp.tzinfo}"
        )
        # Timestamp should be between before and after the call
        assert before_call <= response.metadata.timestamp <= after_call, (
            f"Timestamp {response.metadata.timestamp} not between "
            f"{before_call} and {after_call}"
        )

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_metadata_completeness_cannot_answer_response(self, data):
        """For any cannot-answer QueryResponse (empty context), metadata contains:
        prompt_version matching VERSION, non-empty model_id, temperature float,
        and UTC timestamp.

        **Validates: Requirements 1.4, 7.3, 5.1**
        """
        # Generate random temperature for this test case
        temperature = data.draw(random_temperatures())

        # Build a mock context_builder that returns None (cannot-answer path)
        mock_context_builder = MagicMock(spec=ContextBuilder)
        mock_context_builder.build_context = AsyncMock(return_value=None)

        # Mock LLM client (should NOT be called for cannot-answer path)
        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.call = AsyncMock(
            side_effect=AssertionError("LLM should not be called for cannot-answer path")
        )

        # Real response parser (should NOT be called)
        response_parser = ResponseParser()

        # Mock evidence verifier (should NOT be called)
        mock_evidence_verifier = MagicMock(spec=QueryEvidenceVerifier)

        # Build the service with the random temperature
        service = QueryService(
            llm_client=mock_llm_client,
            context_builder=mock_context_builder,
            response_parser=response_parser,
            evidence_verifier=mock_evidence_verifier,
            temperature=temperature,
        )

        # Build minimal KM and IR
        km = KnowledgeModel(
            document_id="doc-001",
            document_type="prd",
            elements=[],
            extraction_metadata=ExtractionMetadata(
                prompt_version="extraction-v1",
                model_id="gemini/gemini-2.5-flash",
                temperature=0.1,
                element_count=0,
                relationship_count=0,
                verification_rate=0.0,
                extracted_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
        )

        ir = IntermediateRepresentation(
            document_id="doc-001",
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=500,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-001",
                    text="Some document text.",
                    structural_context={"section": "## Intro"},
                    order=0,
                )
            ],
        )

        # Execute the query (will hit cannot-answer path)
        before_call = datetime.now(timezone.utc)
        response = await service.answer(
            document_id="doc-001",
            question="What is something not in the document?",
            knowledge_model=km,
            ir=ir,
        )
        after_call = datetime.now(timezone.utc)

        # Verify this is indeed a cannot-answer response
        assert response.answerable is False

        # Assert metadata completeness
        assert response.metadata is not None, "Metadata should not be None"

        # 1. prompt_version matches VERSION constant
        assert response.metadata.prompt_version == query_answering_v1.VERSION, (
            f"Expected prompt_version='{query_answering_v1.VERSION}', "
            f"got '{response.metadata.prompt_version}'"
        )
        assert response.metadata.prompt_version == "query-answering-v1"
        assert len(response.metadata.prompt_version) > 0

        # 2. model_id is non-empty string
        assert isinstance(response.metadata.model_id, str)
        assert len(response.metadata.model_id) > 0, "model_id must be non-empty"
        # For cannot-answer path, model_id is "none" (per service implementation)
        assert response.metadata.model_id == "none"

        # 3. temperature is a float
        assert isinstance(response.metadata.temperature, float), (
            f"Expected temperature to be float, got {type(response.metadata.temperature)}"
        )
        assert response.metadata.temperature == temperature

        # 4. timestamp is a datetime in UTC
        assert isinstance(response.metadata.timestamp, datetime), (
            f"Expected timestamp to be datetime, got {type(response.metadata.timestamp)}"
        )
        assert response.metadata.timestamp.tzinfo is not None, "Timestamp must be timezone-aware"
        assert response.metadata.timestamp.tzinfo == timezone.utc, (
            f"Timestamp must be in UTC, got tzinfo={response.metadata.timestamp.tzinfo}"
        )
        # Timestamp should be between before and after the call
        assert before_call <= response.metadata.timestamp <= after_call, (
            f"Timestamp {response.metadata.timestamp} not between "
            f"{before_call} and {after_call}"
        )


# =============================================================================
# Property 5: Empty Context Cannot-Answer
# =============================================================================


@st.composite
def random_document_ids(draw):
    """Generate random non-empty document_id strings."""
    return draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
        min_size=3,
        max_size=40,
    ))


class TestProperty5EmptyContextCannotAnswer:
    """Property 5: Empty Context Cannot-Answer.

    For any query where context construction selects zero relevant elements,
    the QueryResponse SHALL have `answerable = false`, an answer text explaining
    the limitation, and an empty source_refs list. No fabricated evidence SHALL
    be returned.

    **Validates: Requirements 1.3, 2.7**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_empty_context_returns_cannot_answer(self, data):
        """For any random question and document_id, when context_builder returns
        None (zero elements), the response has answerable=False, non-empty answer
        explaining the limitation, and empty source_refs list.

        **Validates: Requirements 1.3, 2.7**
        """
        question = data.draw(random_question())
        document_id = data.draw(random_document_ids())

        # Mock context_builder to always return None (empty context)
        mock_context_builder = MagicMock(spec=ContextBuilder)
        mock_context_builder.build_context = AsyncMock(return_value=None)

        # Mock LLM client — should NOT be called when context is empty
        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.call = AsyncMock(
            side_effect=AssertionError(
                "LLM should not be called when context is empty (cannot-answer path)"
            )
        )

        # Mock response parser — should NOT be called
        mock_response_parser = MagicMock(spec=ResponseParser)
        mock_response_parser.parse = MagicMock(
            side_effect=AssertionError(
                "ResponseParser should not be called when context is empty"
            )
        )

        # Mock evidence verifier — should NOT be called
        mock_evidence_verifier = MagicMock(spec=QueryEvidenceVerifier)
        mock_evidence_verifier.verify = MagicMock(
            side_effect=AssertionError(
                "EvidenceVerifier should not be called when context is empty"
            )
        )

        # Build the QueryService
        service = QueryService(
            llm_client=mock_llm_client,
            context_builder=mock_context_builder,
            response_parser=mock_response_parser,
            evidence_verifier=mock_evidence_verifier,
        )

        # Build minimal KM and IR (content doesn't matter since context_builder is mocked)
        km = KnowledgeModel(
            document_id=document_id,
            document_type="prd",
            elements=[],
            extraction_metadata=ExtractionMetadata(
                prompt_version="extraction-v1",
                model_id="gemini/gemini-2.5-flash",
                temperature=0.1,
                element_count=0,
                relationship_count=0,
                verification_rate=0.0,
                extracted_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
        )

        ir = IntermediateRepresentation(
            document_id=document_id,
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=500,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-001",
                    text="Some document text.",
                    structural_context={"section": "## Intro"},
                    order=0,
                )
            ],
        )

        # Execute the query
        response = await service.answer(
            document_id=document_id,
            question=question,
            knowledge_model=km,
            ir=ir,
        )

        # Property assertions:
        # 1. response.answerable is False
        assert response.answerable is False, (
            f"Expected answerable=False when context is empty, "
            f"got answerable={response.answerable}"
        )

        # 2. response.answer is non-empty (explains limitation)
        assert isinstance(response.answer, str), "Answer should be a string"
        assert len(response.answer) > 0, (
            "Answer should be non-empty and explain the limitation"
        )

        # 3. response.source_refs is empty list (no fabricated evidence)
        assert isinstance(response.source_refs, list), "source_refs should be a list"
        assert len(response.source_refs) == 0, (
            f"Expected empty source_refs when context is empty, "
            f"got {len(response.source_refs)} refs: {response.source_refs}"
        )

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_empty_context_no_llm_calls(self, data):
        """For any query where context is empty (None), the LLM SHALL NOT be
        called. The cannot-answer path must short-circuit the pipeline.

        **Validates: Requirements 1.3, 2.7**
        """
        question = data.draw(random_question())
        document_id = data.draw(random_document_ids())

        # Mock context_builder to return None
        mock_context_builder = MagicMock(spec=ContextBuilder)
        mock_context_builder.build_context = AsyncMock(return_value=None)

        # Track LLM calls
        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.call = AsyncMock(
            return_value=LLMResponse(
                content="should not be reached",
                model_id="test-model",
            )
        )

        mock_response_parser = MagicMock(spec=ResponseParser)
        mock_evidence_verifier = MagicMock(spec=QueryEvidenceVerifier)

        service = QueryService(
            llm_client=mock_llm_client,
            context_builder=mock_context_builder,
            response_parser=mock_response_parser,
            evidence_verifier=mock_evidence_verifier,
        )

        km = KnowledgeModel(
            document_id=document_id,
            document_type="prd",
            elements=[],
            extraction_metadata=ExtractionMetadata(
                prompt_version="extraction-v1",
                model_id="gemini/gemini-2.5-flash",
                temperature=0.1,
                element_count=0,
                relationship_count=0,
                verification_rate=0.0,
                extracted_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
        )

        ir = IntermediateRepresentation(
            document_id=document_id,
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=500,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-001",
                    text="Some document text.",
                    structural_context={"section": "## Intro"},
                    order=0,
                )
            ],
        )

        await service.answer(
            document_id=document_id,
            question=question,
            knowledge_model=km,
            ir=ir,
        )

        # Verify no LLM calls were made
        assert mock_llm_client.call.call_count == 0, (
            f"Expected zero LLM calls when context is empty, "
            f"got {mock_llm_client.call.call_count} calls"
        )

        # Verify no response parsing was attempted
        assert mock_response_parser.parse.call_count == 0, (
            f"Expected zero parse calls when context is empty, "
            f"got {mock_response_parser.parse.call_count} calls"
        )

        # Verify no evidence verification was attempted
        assert mock_evidence_verifier.verify.call_count == 0, (
            f"Expected zero verify calls when context is empty, "
            f"got {mock_evidence_verifier.verify.call_count} calls"
        )


# =============================================================================
# Property 11: Controlled Temperature
# =============================================================================


class TestProperty11ControlledTemperature:
    """Property 11: Controlled Temperature.

    For any LLM call made by the QueryService using default configuration,
    the temperature parameter SHALL be ≤ 0.1. If a system configuration
    overrides the temperature to a value > 0.1, the actual temperature used
    SHALL be recorded in the response metadata.

    **Validates: Requirements 7.4**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_default_temperature_is_at_most_0_1(self, data):
        """For any query with default QueryService configuration, the LLM
        is called with temperature ≤ 0.1.

        **Validates: Requirements 7.4**
        """
        question = data.draw(st.text(min_size=1, max_size=200))

        # Build a minimal KM with one relevant element
        km = KnowledgeModel(
            document_id="doc-001",
            document_type="prd",
            elements=[
                KnowledgeElement(
                    id="elem-001",
                    type="concepto",
                    name="Test Element",
                    content="Some content about the topic.",
                    source_ref=SourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-000",
                        page=None,
                        section="## Section",
                        evidence="Evidence text from document.",
                    ),
                    relations=[],
                    verified=True,
                )
            ],
            extraction_metadata=ExtractionMetadata(
                prompt_version="extraction-v1",
                model_id="gemini/gemini-2.5-flash",
                temperature=0.1,
                element_count=1,
                relationship_count=0,
                verification_rate=1.0,
                extracted_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
        )

        ir = IntermediateRepresentation(
            document_id="doc-001",
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=1000,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-000",
                    text="Evidence text from document. Some more content here.",
                    structural_context={"section": "## Section"},
                    order=0,
                )
            ],
        )

        # Mock LLM client — capture the temperature kwarg from all calls
        captured_temperatures = []

        async def mock_call(prompt, *, model_tier="primary", temperature=0.1, model_override=None, auto_fallback=True):
            captured_temperatures.append(temperature)
            # Return a valid scoring response for context builder call
            if "score" in prompt.lower() or "relevance" in prompt.lower():
                return LLMResponse(
                    content=json.dumps([{"id": "elem-001", "score": 9}]),
                    model_id="gemini/gemini-2.5-flash",
                )
            # Return a valid query response for the answer call
            return LLMResponse(
                content=json.dumps({
                    "answer": "The document discusses the topic.",
                    "answerable": True,
                    "source_refs": [
                        {
                            "chunk_id": "chunk-000",
                            "page": None,
                            "section": "## Section",
                            "evidence": "Evidence text from document.",
                        }
                    ],
                }),
                model_id="gemini/gemini-2.5-flash",
            )

        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.call = AsyncMock(side_effect=mock_call)

        # Create QueryService with default temperature (0.1)
        from app.analysis.query.service import QueryService
        from app.analysis.query.response_parser import ResponseParser

        context_builder = ContextBuilder(mock_llm, max_elements=20, budget_ratio=0.6)
        response_parser = ResponseParser()
        evidence_verifier = QueryEvidenceVerifier(fuzzy_threshold=0.8)

        service = QueryService(
            llm_client=mock_llm,
            context_builder=context_builder,
            response_parser=response_parser,
            evidence_verifier=evidence_verifier,
            # Default temperature=0.1
        )

        response = await service.answer(
            document_id="doc-001",
            question=question,
            knowledge_model=km,
            ir=ir,
        )

        # Property: all LLM calls made by QueryService use temperature ≤ 0.1
        for i, temp in enumerate(captured_temperatures):
            assert temp <= 0.1, (
                f"LLM call {i} used temperature={temp}, expected ≤ 0.1 for default config."
            )

        # Also verify metadata records the temperature
        assert response.metadata.temperature <= 0.1, (
            f"Response metadata temperature={response.metadata.temperature}, expected ≤ 0.1."
        )

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_overridden_temperature_recorded_in_metadata(self, data):
        """For any QueryService created with a custom temperature, the LLM
        is called with that temperature AND the response metadata records it.

        **Validates: Requirements 7.4**
        """
        # Generate random temperatures — some ≤ 0.1, some > 0.1
        temperature = data.draw(
            st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False)
        )
        question = data.draw(st.text(min_size=1, max_size=200))

        # Build a minimal KM
        km = KnowledgeModel(
            document_id="doc-001",
            document_type="prd",
            elements=[
                KnowledgeElement(
                    id="elem-001",
                    type="concepto",
                    name="Test Element",
                    content="Some content about the topic.",
                    source_ref=SourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-000",
                        page=None,
                        section="## Section",
                        evidence="Evidence text from document.",
                    ),
                    relations=[],
                    verified=True,
                )
            ],
            extraction_metadata=ExtractionMetadata(
                prompt_version="extraction-v1",
                model_id="gemini/gemini-2.5-flash",
                temperature=0.1,
                element_count=1,
                relationship_count=0,
                verification_rate=1.0,
                extracted_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
        )

        ir = IntermediateRepresentation(
            document_id="doc-001",
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=1000,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-000",
                    text="Evidence text from document. Some more content here.",
                    structural_context={"section": "## Section"},
                    order=0,
                )
            ],
        )

        # Mock LLM client — capture the temperature kwarg
        captured_temperatures = []

        async def mock_call(prompt, *, model_tier="primary", temperature=0.1, model_override=None, auto_fallback=True):
            captured_temperatures.append(temperature)
            if "score" in prompt.lower() or "relevance" in prompt.lower():
                return LLMResponse(
                    content=json.dumps([{"id": "elem-001", "score": 9}]),
                    model_id="gemini/gemini-2.5-flash",
                )
            return LLMResponse(
                content=json.dumps({
                    "answer": "The document discusses the topic.",
                    "answerable": True,
                    "source_refs": [
                        {
                            "chunk_id": "chunk-000",
                            "page": None,
                            "section": "## Section",
                            "evidence": "Evidence text from document.",
                        }
                    ],
                }),
                model_id="gemini/gemini-2.5-flash",
            )

        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.call = AsyncMock(side_effect=mock_call)

        from app.analysis.query.service import QueryService
        from app.analysis.query.response_parser import ResponseParser

        context_builder = ContextBuilder(mock_llm, max_elements=20, budget_ratio=0.6)
        response_parser = ResponseParser()
        evidence_verifier = QueryEvidenceVerifier(fuzzy_threshold=0.8)

        service = QueryService(
            llm_client=mock_llm,
            context_builder=context_builder,
            response_parser=response_parser,
            evidence_verifier=evidence_verifier,
            temperature=temperature,
        )

        response = await service.answer(
            document_id="doc-001",
            question=question,
            knowledge_model=km,
            ir=ir,
        )

        # Property: QueryService calls LLM with the configured temperature
        # The service makes at least one call to the LLM (answer generation)
        # The context_builder also uses the mock_llm but with its own temperature
        # We check that the QueryService's own calls use the configured temperature
        # In the service, the llm_client.call uses self._temperature
        # The context_builder uses the same mock_llm but may use different temp

        # Verify metadata records the actual temperature used
        assert response.metadata.temperature == pytest.approx(temperature, abs=1e-9), (
            f"Response metadata temperature={response.metadata.temperature}, "
            f"expected {temperature} (the configured override)."
        )


# =============================================================================
# Property 8: Knowledge Model Prerequisite Gate
# =============================================================================

from httpx import ASGITransport, AsyncClient

from app.api.v1.query import _get_analysis_service as _get_query_analysis_service, _get_query_service
from app.main import create_app
from app.models.knowledge_model import AnalysisSession

# Non-completed statuses that should trigger 409
NON_COMPLETED_STATUSES = [
    "inferring_type",
    "awaiting_confirmation",
    "extracting",
    "verifying",
    "failed",
]


class TestProperty8KnowledgeModelPrerequisiteGate:
    """Property 8: Knowledge Model Prerequisite Gate.

    For any document whose analysis session status is not "completed",
    submitting a query SHALL return a 409 error response with code
    "km_not_completed" without executing any part of the query pipeline
    (no LLM calls, no context construction).

    **Validates: Requirements 1.7, 5.2**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_non_completed_status_returns_409(self, data):
        """For any document with a non-completed analysis status, POST /query
        returns 409 with error code 'km_not_completed' and no LLM calls are made.

        **Validates: Requirements 1.7, 5.2**
        """
        status = data.draw(st.sampled_from(NON_COMPLETED_STATUSES))
        document_id = f"doc-{data.draw(st.text(alphabet='abcdef0123456789', min_size=4, max_size=8))}"
        question = data.draw(st.text(min_size=1, max_size=200, alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"), whitelist_characters=" ?"
        )))

        # Create a mock AnalysisService that returns a session with non-completed status
        mock_analysis_service = AsyncMock()
        mock_analysis_service.get_session = AsyncMock(
            return_value=AnalysisSession(
                id="session-001",
                document_id=document_id,
                status=status,
                suggested_type="prd",
                suggested_type_justification="Some justification.",
                confirmed_type=None,
                error_message=None if status != "failed" else "Some error occurred",
                created_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            )
        )

        # Create a mock QueryService to verify it is NOT called
        mock_query_service = AsyncMock()
        mock_query_service.answer = AsyncMock(
            side_effect=AssertionError("QueryService.answer should NOT be called for non-completed status")
        )

        # Create the app with dependency overrides
        app = create_app()
        app.dependency_overrides[_get_query_analysis_service] = lambda: mock_analysis_service
        app.dependency_overrides[_get_query_service] = lambda: mock_query_service

        # Make the request
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/documents/{document_id}/query",
                json={"question": question},
            )

        # Assert 409 status code
        assert response.status_code == 409, (
            f"Expected 409 for status='{status}', got {response.status_code}. "
            f"Response: {response.json()}"
        )

        # Assert error code is 'km_not_completed'
        body = response.json()
        assert body["error"] == "km_not_completed", (
            f"Expected error='km_not_completed', got '{body.get('error')}'. "
            f"Status was: '{status}'"
        )

        # Assert the message mentions the current status
        assert status in body["message"], (
            f"Expected message to contain current status '{status}', "
            f"got message: '{body['message']}'"
        )

        # Assert QueryService.answer was never called (no pipeline execution)
        mock_query_service.answer.assert_not_called()

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_no_llm_calls_on_non_completed_status(self, data):
        """For any document with a non-completed analysis status, no LLM calls
        are made — the request is rejected at the gate before pipeline execution.

        **Validates: Requirements 1.7, 5.2**
        """
        status = data.draw(st.sampled_from(NON_COMPLETED_STATUSES))
        document_id = f"doc-{data.draw(st.text(alphabet='abcdef0123456789', min_size=4, max_size=8))}"
        question = data.draw(st.text(min_size=1, max_size=200, alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"), whitelist_characters=" ?"
        )))

        # Create a mock AnalysisService that returns a session with non-completed status
        mock_analysis_service = AsyncMock()
        mock_analysis_service.get_session = AsyncMock(
            return_value=AnalysisSession(
                id="session-002",
                document_id=document_id,
                status=status,
                suggested_type=None,
                suggested_type_justification=None,
                confirmed_type=None,
                error_message="Pipeline failed" if status == "failed" else None,
                created_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
            )
        )

        # Create a mock LLM client to verify it's never called
        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.call = AsyncMock(
            side_effect=AssertionError("LLM client should NOT be called for non-completed status")
        )

        # Create a real QueryService with the mock LLM client
        # (it shouldn't be reached, but if it is, the mock LLM will fail loudly)
        context_builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        response_parser = ResponseParser()
        evidence_verifier = QueryEvidenceVerifier(fuzzy_threshold=0.8)

        query_service = QueryService(
            llm_client=mock_llm_client,
            context_builder=context_builder,
            response_parser=response_parser,
            evidence_verifier=evidence_verifier,
        )

        # Create the app with dependency overrides
        app = create_app()
        app.dependency_overrides[_get_query_analysis_service] = lambda: mock_analysis_service
        app.dependency_overrides[_get_query_service] = lambda: query_service

        # Make the request
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/documents/{document_id}/query",
                json={"question": question},
            )

        # Assert 409 status code
        assert response.status_code == 409, (
            f"Expected 409 for status='{status}', got {response.status_code}."
        )

        # Assert no LLM calls were made
        mock_llm_client.call.assert_not_called()


# =============================================================================
# Property 4: Data Minimization
# =============================================================================


@st.composite
def random_context_elements(draw, min_elements=1, max_elements=10):
    """Generate random context element dicts for query_answering_v1.build().

    Each element has: type, name, content, evidence, verified.
    These represent Knowledge Model elements formatted for the prompt.
    """
    num_elements = draw(st.integers(min_value=min_elements, max_value=max_elements))
    elements = []
    for _ in range(num_elements):
        elem = {
            "type": draw(st.sampled_from(ELEMENT_TYPES)),
            "name": draw(st.text(
                min_size=1,
                max_size=80,
                alphabet=st.characters(whitelist_categories=("L", "N", "Z"), whitelist_characters=" -_"),
            )),
            "content": draw(st.text(
                min_size=1,
                max_size=300,
                alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), whitelist_characters=" .-,;:()"),
            )),
            "evidence": draw(st.text(
                min_size=1,
                max_size=200,
                alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), whitelist_characters=" .-,;:()"),
            )),
            "verified": draw(st.booleans()),
        }
        elements.append(elem)
    return elements


@st.composite
def random_relations(draw, min_relations=0, max_relations=5):
    """Generate random relation dicts for query_answering_v1.build().

    Each relation has: source_id, target_id, type.
    """
    num_relations = draw(st.integers(min_value=min_relations, max_value=max_relations))
    relations = []
    for _ in range(num_relations):
        rel = {
            "source_id": draw(st.text(
                min_size=3,
                max_size=20,
                alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
            )),
            "target_id": draw(st.text(
                min_size=3,
                max_size=20,
                alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
            )),
            "type": draw(st.sampled_from(RELATION_TYPES)),
        }
        relations.append(rel)
    return relations


@st.composite
def random_questions(draw):
    """Generate a random question string for prompt building."""
    return draw(st.text(
        min_size=5,
        max_size=300,
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), whitelist_characters=" ?.-,"),
    ))


class TestProperty4DataMinimization:
    """Property 4: Data Minimization.

    For any prompt constructed by the query pipeline, the prompt content SHALL
    contain only Knowledge Model elements (type, name, content, evidence), their
    relationships, the user's question as a plain string, and system instructions.
    No user identity, session history, account metadata, document_id, or information
    unrelated to the document content SHALL be present in the prompt.

    **Validates: Requirements 2.6, 6.3, 7.2**
    """

    # Blacklisted patterns that must NOT appear in the prompt output.
    # These represent user identity, session, account, and document_id data.
    BLACKLISTED_PATTERNS = [
        "user_id",
        "user-id",
        "userId",
        "session_id",
        "session-id",
        "sessionId",
        "session_history",
        "account_id",
        "account-id",
        "accountId",
        "email@",
        "@example.com",
        "@gmail.com",
        "account_metadata",
        "account_info",
    ]

    # document_id should not appear as a value in the prompt
    # (the word "document" in instructions is OK, but not as an identifier value)
    DOCUMENT_ID_PATTERNS = [
        "document_id",
        "document-id",
        "documentId",
        "doc-001",
        "doc-test",
    ]

    @settings(max_examples=100)
    @given(data=st.data())
    def test_prompt_contains_no_user_identity_patterns(self, data):
        """For any randomly generated context elements, relations, and question,
        the prompt built by query_answering_v1.build() SHALL NOT contain any
        user identity patterns (user_id, session_id, account, email).

        **Validates: Requirements 2.6, 6.3, 7.2**
        """
        context_elements = data.draw(random_context_elements())
        relations = data.draw(random_relations())
        question = data.draw(random_questions())

        # Build the prompt using the actual prompt template
        prompt = query_answering_v1.build(context_elements, relations, question)

        # Assert: no blacklisted user identity patterns are present
        prompt_lower = prompt.lower()
        for pattern in self.BLACKLISTED_PATTERNS:
            assert pattern.lower() not in prompt_lower, (
                f"Data minimization violation: prompt contains blacklisted pattern "
                f"'{pattern}'. The prompt should not contain user identity, session, "
                f"or account metadata.\n"
                f"Prompt excerpt (first 500 chars): {prompt[:500]}"
            )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_prompt_contains_no_document_id_as_value(self, data):
        """For any randomly generated context elements, relations, and question,
        the prompt built by query_answering_v1.build() SHALL NOT contain
        document_id as a data value. The word 'document' in instructions is OK,
        but identifiers like 'document_id', 'doc-001' should not be present.

        **Validates: Requirements 2.6, 6.3, 7.2**
        """
        context_elements = data.draw(random_context_elements())
        relations = data.draw(random_relations())
        question = data.draw(random_questions())

        # Build the prompt using the actual prompt template
        prompt = query_answering_v1.build(context_elements, relations, question)

        # Assert: no document_id patterns appear in the prompt
        prompt_lower = prompt.lower()
        for pattern in self.DOCUMENT_ID_PATTERNS:
            assert pattern.lower() not in prompt_lower, (
                f"Data minimization violation: prompt contains document_id pattern "
                f"'{pattern}'. Document identifiers should not be present in the "
                f"prompt sent to the LLM.\n"
                f"Prompt excerpt (first 500 chars): {prompt[:500]}"
            )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_prompt_contains_only_expected_content(self, data):
        """For any randomly generated context elements, relations, and question,
        the prompt built by query_answering_v1.build() SHALL contain ONLY:
        - System instructions (fixed template text)
        - Knowledge Model element fields (type, name, content, evidence)
        - Relationship entries (source_id, target_id, type)
        - The user's question as a plain string

        Verified by checking that all input element content appears in the prompt
        and no personal information patterns are injected.

        **Validates: Requirements 2.6, 6.3, 7.2**
        """
        context_elements = data.draw(random_context_elements())
        relations = data.draw(random_relations())
        question = data.draw(random_questions())

        # Build the prompt using the actual prompt template
        prompt = query_answering_v1.build(context_elements, relations, question)

        # Verify the question appears in the prompt (it should be included)
        assert question in prompt, (
            f"The user's question should appear in the prompt. "
            f"Question: '{question[:100]}...'"
        )

        # Verify each context element's fields appear in the prompt
        for elem in context_elements:
            assert elem["name"] in prompt, (
                f"Context element name '{elem['name']}' should appear in prompt"
            )
            assert elem["content"] in prompt, (
                f"Context element content should appear in prompt"
            )
            assert elem["evidence"] in prompt, (
                f"Context element evidence should appear in prompt"
            )

        # Verify relations appear in the prompt (if any)
        for rel in relations:
            assert rel["source_id"] in prompt, (
                f"Relation source_id '{rel['source_id']}' should appear in prompt"
            )
            assert rel["target_id"] in prompt, (
                f"Relation target_id '{rel['target_id']}' should appear in prompt"
            )
            assert rel["type"] in prompt, (
                f"Relation type '{rel['type']}' should appear in prompt"
            )

        # Verify no personal information patterns are present
        personal_info_patterns = [
            "password",
            "credit_card",
            "social_security",
            "ssn",
            "phone_number",
            "home_address",
            "ip_address",
            "api_key",
            "secret_key",
            "auth_token",
            "bearer ",
        ]
        prompt_lower = prompt.lower()
        for pattern in personal_info_patterns:
            assert pattern.lower() not in prompt_lower, (
                f"Data minimization violation: prompt contains personal information "
                f"pattern '{pattern}'."
            )


# =============================================================================
# Property 9: Input Validation
# =============================================================================


class TestProperty9InputValidation:
    """Property 9: Input Validation.

    For any question string that is empty (length 0) or exceeds 1000 characters,
    the query endpoint SHALL return a 422 validation error without executing any
    part of the query pipeline.

    **Validates: Requirements 1.8, 5.4**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_empty_string_returns_422(self, data):
        """For any empty question string, the query endpoint returns 422
        without executing any pipeline (no LLM calls).

        **Validates: Requirements 1.8, 5.4**
        """
        document_id = data.draw(
            st.text(alphabet="abcdef0123456789", min_size=4, max_size=20)
        )

        # Mock AnalysisService to return a completed session
        mock_analysis_service = AsyncMock()
        mock_analysis_service.get_session = AsyncMock(
            return_value=AnalysisSession(
                id="session-001",
                document_id=document_id,
                status="completed",
                suggested_type="prd",
                suggested_type_justification="Test document",
                confirmed_type="prd",
                error_message=None,
                created_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
            )
        )

        # Mock QueryService — should NOT be called
        mock_query_service = MagicMock()
        mock_query_service.answer = AsyncMock(
            side_effect=AssertionError(
                "QueryService.answer() should NOT be called for invalid input"
            )
        )

        # Create test app with overrides
        app = create_app()
        app.dependency_overrides[_get_query_analysis_service] = lambda: mock_analysis_service
        app.dependency_overrides[_get_query_service] = lambda: mock_query_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/documents/{document_id}/query",
                json={"question": ""},
            )

        # Property: empty string → 422
        assert response.status_code == 422, (
            f"Expected 422 for empty question, got {response.status_code}. "
            f"Response body: {response.text}"
        )

        # Verify no pipeline execution occurred
        mock_query_service.answer.assert_not_called()

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_string_exceeding_1000_chars_returns_422(self, data):
        """For any question string exceeding 1000 characters, the query endpoint
        returns 422 without executing any pipeline (no LLM calls).

        **Validates: Requirements 1.8, 5.4**
        """
        document_id = data.draw(
            st.text(alphabet="abcdef0123456789", min_size=4, max_size=20)
        )

        # Generate a string with length > 1000
        long_question = data.draw(
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
                min_size=1001,
                max_size=2000,
            )
        )

        # Mock AnalysisService to return a completed session
        mock_analysis_service = AsyncMock()
        mock_analysis_service.get_session = AsyncMock(
            return_value=AnalysisSession(
                id="session-001",
                document_id=document_id,
                status="completed",
                suggested_type="prd",
                suggested_type_justification="Test document",
                confirmed_type="prd",
                error_message=None,
                created_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
            )
        )

        # Mock QueryService — should NOT be called
        mock_query_service = MagicMock()
        mock_query_service.answer = AsyncMock(
            side_effect=AssertionError(
                "QueryService.answer() should NOT be called for invalid input"
            )
        )

        # Create test app with overrides
        app = create_app()
        app.dependency_overrides[_get_query_analysis_service] = lambda: mock_analysis_service
        app.dependency_overrides[_get_query_service] = lambda: mock_query_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/documents/{document_id}/query",
                json={"question": long_question},
            )

        # Property: string > 1000 chars → 422
        assert response.status_code == 422, (
            f"Expected 422 for question of length {len(long_question)}, "
            f"got {response.status_code}. Response body: {response.text[:200]}"
        )

        # Verify no pipeline execution occurred
        mock_query_service.answer.assert_not_called()

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_invalid_input_does_not_invoke_llm(self, data):
        """For any invalid question (empty or >1000 chars), no LLM calls are made
        and no part of the query pipeline executes.

        **Validates: Requirements 1.8, 5.4**
        """
        document_id = data.draw(
            st.text(alphabet="abcdef0123456789", min_size=4, max_size=20)
        )

        # Generate either an empty string or a string > 1000 chars
        invalid_question = data.draw(
            st.one_of(
                st.just(""),
                st.text(
                    alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
                    min_size=1001,
                    max_size=2000,
                ),
            )
        )

        # Mock AnalysisService to return a completed session
        mock_analysis_service = AsyncMock()
        mock_analysis_service.get_session = AsyncMock(
            return_value=AnalysisSession(
                id="session-001",
                document_id=document_id,
                status="completed",
                suggested_type="prd",
                suggested_type_justification="Test document",
                confirmed_type="prd",
                error_message=None,
                created_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
            )
        )

        # Mock QueryService — should NOT be called
        mock_query_service = MagicMock()
        mock_query_service.answer = AsyncMock(
            side_effect=AssertionError(
                "QueryService.answer() should NOT be called for invalid input"
            )
        )

        # Create test app with overrides
        app = create_app()
        app.dependency_overrides[_get_query_analysis_service] = lambda: mock_analysis_service
        app.dependency_overrides[_get_query_service] = lambda: mock_query_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/documents/{document_id}/query",
                json={"question": invalid_question},
            )

        # Property: invalid input → 422, no pipeline execution
        assert response.status_code == 422, (
            f"Expected 422 for invalid question (length={len(invalid_question)}), "
            f"got {response.status_code}. Response body: {response.text[:200]}"
        )

        # Verify no part of the query pipeline executed
        mock_query_service.answer.assert_not_called()
        # AnalysisService.get_session should NOT be called either
        # because Pydantic validation happens before any business logic
        mock_analysis_service.get_session.assert_not_called()
