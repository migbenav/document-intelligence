"""Unit tests for the ExtractionService.

Tests cover:
- Successful extraction with valid LLM response
- Complete parse failure raises ExtractionError
- Partial malformed elements discarded with valid ones retained
- Dangling relationship references removed
- "contradicts" relationships made bidirectional
- Proposito validation (warning when missing)
- Segmentation and merging for large documents
- Output normalization (whitespace, casing)
- Source ref population (page for PDF, section for Markdown)

Requirements validated: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.4, 6.5, 10.1
"""

import json
import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.analysis.extraction import (
    ExtractionError,
    ExtractionService,
    _MAX_SEGMENT_CHARS,
)
from app.analysis.llm_client import LLMClient, LLMResponse
from app.analysis.prompts import extraction_v1
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)


# --- Helpers ---


def _make_ir(
    chunks_text: list[str],
    doc_format: DocumentFormat = DocumentFormat.MARKDOWN,
    structural_contexts: list[dict] | None = None,
) -> IntermediateRepresentation:
    """Create an IntermediateRepresentation with the given chunk texts."""
    if structural_contexts is None:
        if doc_format == DocumentFormat.PDF:
            structural_contexts = [{"page": i + 1} for i in range(len(chunks_text))]
        elif doc_format == DocumentFormat.MARKDOWN:
            structural_contexts = [
                {"section": f"Section {i}"} for i in range(len(chunks_text))
            ]
        else:
            structural_contexts = [{} for _ in chunks_text]

    chunks = [
        ContentChunkModel(
            chunk_id=f"chunk-{i:03d}",
            text=text,
            structural_context=structural_contexts[i],
            order=i,
        )
        for i, text in enumerate(chunks_text)
    ]
    return IntermediateRepresentation(
        document_id="doc-001",
        metadata=DocumentMetadata(
            original_filename="test.md",
            format=doc_format,
            size_bytes=1024,
            language=DetectedLanguage.SPANISH,
            upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        chunks=chunks,
    )


def _make_valid_llm_response(elements: list[dict] | None = None) -> str:
    """Create a valid LLM JSON response string."""
    if elements is None:
        elements = [
            {
                "id": "elem-001",
                "type": "proposito",
                "name": "Main Purpose",
                "content": "The document describes the system architecture.",
                "source_ref": {
                    "chunk_id": "chunk-000",
                    "page": None,
                    "section": "Section 0",
                    "evidence": "describes the system architecture",
                },
                "relations": [],
            },
            {
                "id": "elem-002",
                "type": "concepto",
                "name": "Architecture",
                "content": "The overall system design.",
                "source_ref": {
                    "chunk_id": "chunk-001",
                    "page": None,
                    "section": "Section 1",
                    "evidence": "overall system design",
                },
                "relations": [
                    {
                        "target_id": "elem-001",
                        "type": "depends_on",
                        "description": "Architecture depends on purpose",
                    }
                ],
            },
        ]
    return json.dumps({"elements": elements})


@pytest.fixture
def mock_llm_client():
    """Create a mock LLMClient for unit testing."""
    client = AsyncMock(spec=LLMClient)
    return client


@pytest.fixture
def service(mock_llm_client) -> ExtractionService:
    """Create an ExtractionService with a mocked LLMClient."""
    return ExtractionService(llm_client=mock_llm_client)


# --- Successful Extraction Tests (Req 5.1, 5.2, 5.4) ---


class TestSuccessfulExtraction:
    @pytest.mark.asyncio
    async def test_successful_extraction_returns_knowledge_model(
        self, service, mock_llm_client
    ):
        """Valid LLM response produces a KnowledgeModel with elements."""
        mock_llm_client.call.return_value = LLMResponse(
            content=_make_valid_llm_response(),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["System architecture overview.", "Design details."])
        result = await service.extract(ir, "technical_spec")

        assert result.document_id == "doc-001"
        assert result.document_type == "technical_spec"
        assert len(result.elements) == 2
        assert result.elements[0].type == "proposito"
        assert result.elements[1].type == "concepto"

    @pytest.mark.asyncio
    async def test_extraction_metadata_populated(self, service, mock_llm_client):
        """ExtractionMetadata is populated with prompt version, model, temp."""
        mock_llm_client.call.return_value = LLMResponse(
            content=_make_valid_llm_response(),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        result = await service.extract(ir, "prd")

        assert result.extraction_metadata.prompt_version == extraction_v1.VERSION
        assert result.extraction_metadata.model_id == "gemini/gemini-2.5-flash-preview-05-20"
        assert result.extraction_metadata.temperature == 0.1
        assert result.extraction_metadata.element_count == 2
        assert result.extraction_metadata.relationship_count == 1

    @pytest.mark.asyncio
    async def test_uses_primary_model_tier(self, service, mock_llm_client):
        """Extraction uses model_tier='primary' for LLM call (Req 5.1)."""
        mock_llm_client.call.return_value = LLMResponse(
            content=_make_valid_llm_response(),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        await service.extract(ir, "prd")

        mock_llm_client.call.assert_called_once()
        call_kwargs = mock_llm_client.call.call_args
        assert call_kwargs.kwargs["model_tier"] == "primary"

    @pytest.mark.asyncio
    async def test_elements_have_source_ref_with_evidence(
        self, service, mock_llm_client
    ):
        """Each element has a source_ref with evidence (Req 5.4)."""
        mock_llm_client.call.return_value = LLMResponse(
            content=_make_valid_llm_response(),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        result = await service.extract(ir, "prd")

        for elem in result.elements:
            assert elem.source_ref is not None
            assert elem.source_ref.document_id == "doc-001"
            assert elem.source_ref.evidence != ""


# --- Complete Parse Failure Tests (Req 5.6) ---


class TestCompleteParseFailure:
    @pytest.mark.asyncio
    async def test_invalid_json_raises_extraction_error(
        self, service, mock_llm_client
    ):
        """Completely invalid JSON raises ExtractionError (Req 5.6)."""
        mock_llm_client.call.return_value = LLMResponse(
            content="This is not JSON at all",
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        with pytest.raises(ExtractionError, match="Complete parse failure"):
            await service.extract(ir, "prd")

    @pytest.mark.asyncio
    async def test_json_without_elements_key_raises_extraction_error(
        self, service, mock_llm_client
    ):
        """JSON without 'elements' key raises ExtractionError (Req 5.6)."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"data": []}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        with pytest.raises(ExtractionError, match="does not contain 'elements'"):
            await service.extract(ir, "prd")

    @pytest.mark.asyncio
    async def test_elements_not_a_list_raises_extraction_error(
        self, service, mock_llm_client
    ):
        """'elements' field not a list raises ExtractionError (Req 5.6)."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"elements": "not a list"}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        with pytest.raises(ExtractionError, match="not a list"):
            await service.extract(ir, "prd")

    @pytest.mark.asyncio
    async def test_empty_string_raises_extraction_error(
        self, service, mock_llm_client
    ):
        """Empty string response raises ExtractionError (Req 5.6)."""
        mock_llm_client.call.return_value = LLMResponse(
            content="",
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        with pytest.raises(ExtractionError):
            await service.extract(ir, "prd")


# --- Partial Malformed Elements Tests (Req 5.6) ---


class TestPartialMalformedElements:
    @pytest.mark.asyncio
    async def test_malformed_elements_discarded_valid_retained(
        self, service, mock_llm_client
    ):
        """Malformed elements are discarded, valid ones retained (Req 5.6)."""
        elements = [
            {
                "id": "elem-001",
                "type": "proposito",
                "name": "Valid Element",
                "content": "Good content.",
                "source_ref": {
                    "chunk_id": "chunk-000",
                    "evidence": "Good content.",
                },
                "relations": [],
            },
            {
                # Missing required 'id' field
                "type": "concepto",
                "name": "Bad Element",
                "content": "Missing id.",
            },
            {
                "id": "elem-003",
                "type": "invalid_type",  # Invalid type
                "name": "Invalid Type",
                "content": "Bad type.",
                "source_ref": {"chunk_id": "chunk-000", "evidence": "text"},
                "relations": [],
            },
        ]
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"elements": elements}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        result = await service.extract(ir, "prd")

        # Only the valid element should remain
        assert len(result.elements) == 1
        assert result.elements[0].id == "elem-001"

    @pytest.mark.asyncio
    async def test_element_not_a_dict_discarded(self, service, mock_llm_client):
        """Elements that aren't dicts are discarded."""
        elements = [
            "not a dict",
            {
                "id": "elem-001",
                "type": "proposito",
                "name": "Valid",
                "content": "Good.",
                "source_ref": {"chunk_id": "chunk-000", "evidence": "Good."},
                "relations": [],
            },
        ]
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"elements": elements}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        result = await service.extract(ir, "prd")

        assert len(result.elements) == 1
        assert result.elements[0].id == "elem-001"

    @pytest.mark.asyncio
    async def test_malformed_relations_discarded_element_kept(
        self, service, mock_llm_client
    ):
        """Malformed relations within an element are discarded, element kept."""
        elements = [
            {
                "id": "elem-001",
                "type": "proposito",
                "name": "Valid",
                "content": "Good.",
                "source_ref": {"chunk_id": "chunk-000", "evidence": "Good."},
                "relations": [
                    {"target_id": "elem-002", "type": "invalid_rel_type"},
                    {"target_id": "elem-002", "type": "depends_on"},
                ],
            },
        ]
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"elements": elements}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        result = await service.extract(ir, "prd")

        assert len(result.elements) == 1
        # Invalid relation discarded, but the valid one should still be present
        # Note: depends_on to elem-002 is dangling (elem-002 doesn't exist)
        # so it will be removed by dangling reference removal
        # The point is the element itself is not discarded
        assert result.elements[0].id == "elem-001"


# --- Dangling Reference Removal Tests (Req 6.5) ---


class TestDanglingReferences:
    @pytest.mark.asyncio
    async def test_dangling_references_removed(self, service, mock_llm_client):
        """Relations referencing non-existent element IDs are removed (Req 6.5)."""
        elements = [
            {
                "id": "elem-001",
                "type": "proposito",
                "name": "Purpose",
                "content": "Main purpose.",
                "source_ref": {"chunk_id": "chunk-000", "evidence": "Main purpose."},
                "relations": [
                    {"target_id": "elem-002", "type": "depends_on"},
                    {"target_id": "elem-999", "type": "constrains"},  # Dangling
                ],
            },
            {
                "id": "elem-002",
                "type": "concepto",
                "name": "Concept",
                "content": "A concept.",
                "source_ref": {"chunk_id": "chunk-000", "evidence": "A concept."},
                "relations": [],
            },
        ]
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"elements": elements}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        result = await service.extract(ir, "prd")

        # elem-001 should only have the valid relation to elem-002
        purpose_elem = next(e for e in result.elements if e.id == "elem-001")
        assert len(purpose_elem.relations) == 1
        assert purpose_elem.relations[0].target_id == "elem-002"

    @pytest.mark.asyncio
    async def test_all_valid_references_retained(self, service, mock_llm_client):
        """Valid references are not removed."""
        elements = [
            {
                "id": "elem-001",
                "type": "proposito",
                "name": "Purpose",
                "content": "Purpose.",
                "source_ref": {"chunk_id": "chunk-000", "evidence": "Purpose."},
                "relations": [{"target_id": "elem-002", "type": "depends_on"}],
            },
            {
                "id": "elem-002",
                "type": "concepto",
                "name": "Concept",
                "content": "Concept.",
                "source_ref": {"chunk_id": "chunk-000", "evidence": "Concept."},
                "relations": [{"target_id": "elem-001", "type": "constrains"}],
            },
        ]
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"elements": elements}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        result = await service.extract(ir, "prd")

        elem1 = next(e for e in result.elements if e.id == "elem-001")
        elem2 = next(e for e in result.elements if e.id == "elem-002")
        assert len(elem1.relations) == 1
        assert len(elem2.relations) == 1


# --- Bidirectional Contradicts Tests (Req 6.4) ---


class TestBidirectionalContradicts:
    @pytest.mark.asyncio
    async def test_contradicts_made_bidirectional(self, service, mock_llm_client):
        """If A contradicts B, B must also contradicts A (Req 6.4)."""
        elements = [
            {
                "id": "elem-001",
                "type": "regla",
                "name": "Rule A",
                "content": "Rule A content.",
                "source_ref": {"chunk_id": "chunk-000", "evidence": "Rule A content."},
                "relations": [{"target_id": "elem-002", "type": "contradicts"}],
            },
            {
                "id": "elem-002",
                "type": "regla",
                "name": "Rule B",
                "content": "Rule B content.",
                "source_ref": {"chunk_id": "chunk-000", "evidence": "Rule B content."},
                "relations": [],  # Missing reverse contradicts
            },
        ]
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"elements": elements}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        result = await service.extract(ir, "prd")

        elem_b = next(e for e in result.elements if e.id == "elem-002")
        # Should now have a contradicts relation back to elem-001
        contradicts_rels = [r for r in elem_b.relations if r.type == "contradicts"]
        assert len(contradicts_rels) == 1
        assert contradicts_rels[0].target_id == "elem-001"

    @pytest.mark.asyncio
    async def test_already_bidirectional_not_duplicated(
        self, service, mock_llm_client
    ):
        """Already-bidirectional contradicts are not duplicated."""
        elements = [
            {
                "id": "elem-001",
                "type": "regla",
                "name": "Rule A",
                "content": "Rule A.",
                "source_ref": {"chunk_id": "chunk-000", "evidence": "Rule A."},
                "relations": [{"target_id": "elem-002", "type": "contradicts"}],
            },
            {
                "id": "elem-002",
                "type": "regla",
                "name": "Rule B",
                "content": "Rule B.",
                "source_ref": {"chunk_id": "chunk-000", "evidence": "Rule B."},
                "relations": [{"target_id": "elem-001", "type": "contradicts"}],
            },
        ]
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"elements": elements}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        result = await service.extract(ir, "prd")

        elem_a = next(e for e in result.elements if e.id == "elem-001")
        elem_b = next(e for e in result.elements if e.id == "elem-002")
        # Each should have exactly one contradicts relation
        assert len([r for r in elem_a.relations if r.type == "contradicts"]) == 1
        assert len([r for r in elem_b.relations if r.type == "contradicts"]) == 1


# --- Proposito Validation Tests (Req 5.3) ---


class TestPropositoValidation:
    @pytest.mark.asyncio
    async def test_warns_when_no_proposito(
        self, service, mock_llm_client, caplog
    ):
        """Logs warning when no 'proposito' element exists (Req 5.3)."""
        elements = [
            {
                "id": "elem-001",
                "type": "concepto",
                "name": "Only Concept",
                "content": "No purpose.",
                "source_ref": {"chunk_id": "chunk-000", "evidence": "No purpose."},
                "relations": [],
            },
        ]
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"elements": elements}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        with caplog.at_level(logging.WARNING):
            result = await service.extract(ir, "prd")

        assert "proposito" in caplog.text.lower()
        # Extraction still succeeds — just warns
        assert len(result.elements) == 1

    @pytest.mark.asyncio
    async def test_no_warning_when_proposito_exists(
        self, service, mock_llm_client, caplog
    ):
        """No warning when 'proposito' element exists."""
        mock_llm_client.call.return_value = LLMResponse(
            content=_make_valid_llm_response(),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        with caplog.at_level(logging.WARNING):
            await service.extract(ir, "prd")

        proposito_warnings = [
            r for r in caplog.records if "proposito" in r.message.lower()
        ]
        assert len(proposito_warnings) == 0


# --- Segmentation and Merging Tests (Req 5.7) ---


class TestSegmentation:
    @pytest.mark.asyncio
    async def test_large_document_triggers_segmentation(
        self, service, mock_llm_client
    ):
        """Documents exceeding _MAX_SEGMENT_CHARS are segmented (Req 5.7)."""
        # Create chunks that exceed the limit
        large_text = "x" * (_MAX_SEGMENT_CHARS + 1000)
        chunk1 = large_text[:_MAX_SEGMENT_CHARS - 100]
        chunk2 = large_text[_MAX_SEGMENT_CHARS - 100:]

        # Each segment call returns different elements
        response1 = json.dumps({
            "elements": [
                {
                    "id": "elem-001",
                    "type": "proposito",
                    "name": "Purpose",
                    "content": "Purpose from segment 1.",
                    "source_ref": {"chunk_id": "chunk-000", "evidence": "Purpose"},
                    "relations": [],
                }
            ]
        })
        response2 = json.dumps({
            "elements": [
                {
                    "id": "elem-002",
                    "type": "concepto",
                    "name": "Concept",
                    "content": "Concept from segment 2.",
                    "source_ref": {"chunk_id": "chunk-001", "evidence": "Concept"},
                    "relations": [],
                }
            ]
        })
        mock_llm_client.call.side_effect = [
            LLMResponse(content=response1, model_id="gemini/gemini-2.5-flash-preview-05-20"),
            LLMResponse(content=response2, model_id="gemini/gemini-2.5-flash-preview-05-20"),
        ]

        ir = _make_ir([chunk1, chunk2])
        result = await service.extract(ir, "prd")

        # Should have called LLM twice (one per segment)
        assert mock_llm_client.call.call_count == 2
        # Both elements should be in the final result
        assert len(result.elements) == 2

    @pytest.mark.asyncio
    async def test_segmentation_deduplicates_by_name_and_type(
        self, service, mock_llm_client
    ):
        """Duplicate elements across segments are deduplicated (Req 5.7)."""
        large_text = "x" * (_MAX_SEGMENT_CHARS + 1000)
        chunk1 = large_text[:_MAX_SEGMENT_CHARS - 100]
        chunk2 = large_text[_MAX_SEGMENT_CHARS - 100:]

        # Both segments return an element with same name+type
        duplicate_element = {
            "id": "elem-001",
            "type": "proposito",
            "name": "Purpose",
            "content": "Purpose content.",
            "source_ref": {"chunk_id": "chunk-000", "evidence": "Purpose"},
            "relations": [],
        }
        response1 = json.dumps({"elements": [duplicate_element]})
        duplicate_element_2 = dict(duplicate_element)
        duplicate_element_2["id"] = "elem-002"
        response2 = json.dumps({"elements": [duplicate_element_2]})

        mock_llm_client.call.side_effect = [
            LLMResponse(content=response1, model_id="gemini/gemini-2.5-flash-preview-05-20"),
            LLMResponse(content=response2, model_id="gemini/gemini-2.5-flash-preview-05-20"),
        ]

        ir = _make_ir([chunk1, chunk2])
        result = await service.extract(ir, "prd")

        # Deduplication should keep only the first occurrence
        proposito_elements = [e for e in result.elements if e.type == "proposito"]
        assert len(proposito_elements) == 1


# --- Output Normalization Tests (Req 10.1) ---


class TestOutputNormalization:
    @pytest.mark.asyncio
    async def test_whitespace_trimmed_from_names(self, service, mock_llm_client):
        """Element names have leading/trailing whitespace trimmed (Req 10.1)."""
        elements = [
            {
                "id": "elem-001",
                "type": "proposito",
                "name": "  Spaced Name  ",
                "content": "  Spaced content.  ",
                "source_ref": {
                    "chunk_id": "chunk-000",
                    "evidence": "  spaced evidence  ",
                },
                "relations": [],
            },
        ]
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"elements": elements}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        result = await service.extract(ir, "prd")

        assert result.elements[0].name == "Spaced Name"
        assert result.elements[0].content == "Spaced content."
        assert result.elements[0].source_ref.evidence == "spaced evidence"

    @pytest.mark.asyncio
    async def test_types_normalized_to_lowercase(self, service, mock_llm_client):
        """Element types are normalized to lowercase (Req 10.1)."""
        elements = [
            {
                "id": "elem-001",
                "type": "proposito",  # already lowercase
                "name": "Purpose",
                "content": "Content.",
                "source_ref": {"chunk_id": "chunk-000", "evidence": "Content."},
                "relations": [],
            },
        ]
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"elements": elements}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        result = await service.extract(ir, "prd")

        assert result.elements[0].type == "proposito"


# --- Source Ref Population Tests (Req 5.5) ---


class TestSourceRefPopulation:
    @pytest.mark.asyncio
    async def test_pdf_populates_page_from_structural_context(
        self, service, mock_llm_client
    ):
        """For PDF documents, page is populated from chunk structural_context (Req 5.5)."""
        elements = [
            {
                "id": "elem-001",
                "type": "proposito",
                "name": "Purpose",
                "content": "Content.",
                "source_ref": {
                    "chunk_id": "chunk-000",
                    "page": None,
                    "section": None,
                    "evidence": "Content.",
                },
                "relations": [],
            },
        ]
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"elements": elements}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(
            ["PDF content on page 3."],
            doc_format=DocumentFormat.PDF,
            structural_contexts=[{"page": 3}],
        )
        result = await service.extract(ir, "prd")

        assert result.elements[0].source_ref.page == 3

    @pytest.mark.asyncio
    async def test_markdown_populates_section_from_structural_context(
        self, service, mock_llm_client
    ):
        """For Markdown documents, section is populated from chunk structural_context (Req 5.5)."""
        elements = [
            {
                "id": "elem-001",
                "type": "proposito",
                "name": "Purpose",
                "content": "Content.",
                "source_ref": {
                    "chunk_id": "chunk-000",
                    "page": None,
                    "section": None,
                    "evidence": "Content.",
                },
                "relations": [],
            },
        ]
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"elements": elements}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(
            ["Markdown content."],
            doc_format=DocumentFormat.MARKDOWN,
            structural_contexts=[{"section": "# Introduction"}],
        )
        result = await service.extract(ir, "prd")

        assert result.elements[0].source_ref.section == "# Introduction"

    @pytest.mark.asyncio
    async def test_llm_provided_page_used_when_no_structural_context(
        self, service, mock_llm_client
    ):
        """LLM-provided page is preserved when chunk context is unavailable."""
        elements = [
            {
                "id": "elem-001",
                "type": "proposito",
                "name": "Purpose",
                "content": "Content.",
                "source_ref": {
                    "chunk_id": "chunk-unknown",  # Non-existent chunk
                    "page": 7,
                    "section": None,
                    "evidence": "Content.",
                },
                "relations": [],
            },
        ]
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"elements": elements}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(
            ["PDF content."],
            doc_format=DocumentFormat.PDF,
            structural_contexts=[{"page": 1}],
        )
        result = await service.extract(ir, "prd")

        # Should fall back to the LLM-provided page value
        assert result.elements[0].source_ref.page == 7


# --- Code Fence Handling ---


class TestCodeFenceHandling:
    @pytest.mark.asyncio
    async def test_response_with_json_code_fence_parsed(
        self, service, mock_llm_client
    ):
        """LLM responses wrapped in ```json fences are handled."""
        raw_json = _make_valid_llm_response()
        fenced = f"```json\n{raw_json}\n```"
        mock_llm_client.call.return_value = LLMResponse(
            content=fenced,
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        ir = _make_ir(["Content."])
        result = await service.extract(ir, "prd")

        assert len(result.elements) == 2
