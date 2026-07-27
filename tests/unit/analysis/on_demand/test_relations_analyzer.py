"""Unit tests for RelationsAnalyzer (Section Relations, C3.2).

Tests cover: successful parse, invalid JSON, validation errors, timeout,
prompt construction, language parameter, index_result injection,
and relation type vocabulary validation.
All tests mock LLMClient.
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.analysis.llm_client import LLMResponse
from app.analysis.on_demand.models import IndexResult, RelationsResult, StructureNode
from app.analysis.on_demand.relations_analyzer import (
    RelationsAnalyzer,
    RelationsAnalysisError,
    _build_structure_tree_section,
    _collect_nodes,
    _extract_json,
)
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)


def _make_ir(chunks: list[ContentChunkModel] | None = None) -> IntermediateRepresentation:
    """Build a minimal IR for testing."""
    if chunks is None:
        chunks = [
            ContentChunkModel(
                chunk_id="c1",
                text="Definitions of key terms.",
                structural_context={"section": "Definitions"},
                order=0,
            ),
            ContentChunkModel(
                chunk_id="c2",
                text="Procedures for requesting purchases.",
                structural_context={"section": "Procedures"},
                order=1,
            ),
            ContentChunkModel(
                chunk_id="c3",
                text="Restrictions on purchase amounts.",
                structural_context={"section": "Restrictions"},
                order=2,
            ),
        ]
    return IntermediateRepresentation(
        document_id="doc-002",
        metadata=DocumentMetadata(
            original_filename="procurement.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=4096,
            language=DetectedLanguage.SPANISH,
            upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        chunks=chunks,
    )


def _valid_relations_response() -> dict:
    """Return a valid RelationsResult JSON structure."""
    return {
        "relations": [
            {
                "source_section": "Restrictions",
                "target_section": "Procedures",
                "type": "constrains",
                "description": "The restrictions limit purchase procedures.",
                "source_ref": {
                    "chunk_ids": ["c3"],
                    "text_excerpt": "Restrictions on purchase amounts.",
                    "section": "Restrictions",
                },
            },
            {
                "source_section": "Procedures",
                "target_section": "Definitions",
                "type": "depends_on",
                "description": "Procedures require understanding key terms.",
                "source_ref": {
                    "chunk_ids": ["c2"],
                    "text_excerpt": "Procedures for requesting purchases.",
                    "section": "Procedures",
                },
            },
        ]
    }


def _make_index_result() -> IndexResult:
    """Build a minimal IndexResult for testing index_result injection."""
    return IndexResult(
        tree=[
            StructureNode(
                id="node-1",
                title="Definitions",
                level=1,
                role="defines",
                question_answered="What terms are used?",
                source_ref=None,
                children=[
                    StructureNode(
                        id="node-1.1",
                        title="Key Terms",
                        level=2,
                        role="lists",
                        question_answered="What are the key terms?",
                        source_ref=None,
                        children=[],
                    )
                ],
            ),
            StructureNode(
                id="node-2",
                title="Procedures",
                level=1,
                role="establishes",
                question_answered="How are purchases made?",
                source_ref=None,
                children=[],
            ),
            StructureNode(
                id="node-3",
                title="Restrictions",
                level=1,
                role="restricts",
                question_answered="What limits apply?",
                source_ref=None,
                children=[],
            ),
        ]
    )


def _make_mock_llm_client(response_content: str) -> MagicMock:
    """Create a mock LLMClient that returns the given content."""
    mock_client = MagicMock()
    mock_client.call = AsyncMock(
        return_value=LLMResponse(
            content=response_content, model_id="gemini/gemini-2.5-flash"
        )
    )
    return mock_client


class TestExtractJson:
    """Tests for the JSON extraction helper."""

    def test_plain_json(self):
        text = '{"relations": []}'
        assert _extract_json(text) == '{"relations": []}'

    def test_json_in_fences(self):
        text = '```json\n{"relations": []}\n```'
        assert _extract_json(text) == '{"relations": []}'

    def test_json_in_fences_no_language(self):
        text = '```\n{"relations": []}\n```'
        assert _extract_json(text) == '{"relations": []}'

    def test_strips_whitespace(self):
        text = '  {"relations": []}  '
        assert _extract_json(text) == '{"relations": []}'


class TestCollectNodes:
    """Tests for the node collection helper."""

    def test_flat_tree(self):
        index = _make_index_result()
        nodes = _collect_nodes(index.tree)
        ids = [n[0] for n in nodes]
        assert "node-1" in ids
        assert "node-2" in ids
        assert "node-3" in ids

    def test_includes_nested_children(self):
        index = _make_index_result()
        nodes = _collect_nodes(index.tree)
        ids = [n[0] for n in nodes]
        assert "node-1.1" in ids

    def test_preserves_titles(self):
        index = _make_index_result()
        nodes = _collect_nodes(index.tree)
        titles = [n[1] for n in nodes]
        assert "Definitions" in titles
        assert "Key Terms" in titles
        assert "Procedures" in titles
        assert "Restrictions" in titles


class TestBuildStructureTreeSection:
    """Tests for the structure tree section builder."""

    def test_format(self):
        index = _make_index_result()
        section = _build_structure_tree_section(index)
        assert section.startswith("--- STRUCTURE TREE NODES ---")
        assert '- node-1: "Definitions"' in section
        assert '- node-1.1: "Key Terms"' in section
        assert '- node-2: "Procedures"' in section
        assert '- node-3: "Restrictions"' in section


class TestRelationsAnalyzerSuccess:
    """Tests for successful analysis scenarios."""

    @pytest.mark.asyncio
    async def test_successful_analysis(self):
        """A valid JSON response produces a valid RelationsResult."""
        response_data = _valid_relations_response()
        mock_client = _make_mock_llm_client(json.dumps(response_data))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        result = await analyzer.analyze(ir, language="es")

        assert isinstance(result, RelationsResult)
        assert len(result.relations) == 2
        assert result.relations[0].type == "constrains"
        assert result.relations[0].source_section == "Restrictions"
        assert result.relations[0].target_section == "Procedures"
        assert result.relations[1].type == "depends_on"

    @pytest.mark.asyncio
    async def test_response_with_json_fences(self):
        """LLM response wrapped in ```json fences is handled correctly."""
        response_data = _valid_relations_response()
        content = f"```json\n{json.dumps(response_data)}\n```"
        mock_client = _make_mock_llm_client(content)
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        result = await analyzer.analyze(ir, language="en")

        assert isinstance(result, RelationsResult)
        assert len(result.relations) == 2

    @pytest.mark.asyncio
    async def test_prompt_includes_document_text(self):
        """The prompt sent to the LLM includes the full document text."""
        mock_client = _make_mock_llm_client(json.dumps({"relations": []}))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "[Section: Definitions] (chunk 0)" in prompt
        assert "Definitions of key terms." in prompt
        assert "[Section: Procedures] (chunk 1)" in prompt
        assert "[Section: Restrictions] (chunk 2)" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_language(self):
        """The prompt includes the response language instruction."""
        mock_client = _make_mock_llm_client(json.dumps({"relations": []}))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "Respond in es" in prompt

    @pytest.mark.asyncio
    async def test_llm_called_with_correct_parameters(self):
        """LLMClient.call is invoked with expected parameters."""
        mock_client = _make_mock_llm_client(json.dumps({"relations": []}))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(
            ir, language="en", model_override="custom-model", auto_fallback=False
        )

        mock_client.call.assert_called_once()
        call_kwargs = mock_client.call.call_args[1]
        assert call_kwargs["model_tier"] == "primary"
        assert call_kwargs["temperature"] == 0.1
        assert call_kwargs["model_override"] == "custom-model"
        assert call_kwargs["auto_fallback"] is False

    @pytest.mark.asyncio
    async def test_prompt_version_property(self):
        """The analyzer exposes the prompt version."""
        mock_client = MagicMock()
        analyzer = RelationsAnalyzer(mock_client)

        assert analyzer.prompt_version == "section-relations-v1"

    @pytest.mark.asyncio
    async def test_empty_relations_accepted(self):
        """An empty relations list is a valid result."""
        mock_client = _make_mock_llm_client(json.dumps({"relations": []}))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        result = await analyzer.analyze(ir, language="es")

        assert isinstance(result, RelationsResult)
        assert len(result.relations) == 0


class TestRelationsAnalyzerWithIndex:
    """Tests for behavior when index_result is provided."""

    @pytest.mark.asyncio
    async def test_prompt_includes_structure_tree_nodes(self):
        """When index_result is provided, the prompt includes node IDs."""
        mock_client = _make_mock_llm_client(json.dumps({"relations": []}))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()
        index = _make_index_result()

        await analyzer.analyze(ir, language="es", index_result=index)

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "--- STRUCTURE TREE NODES ---" in prompt
        assert '- node-1: "Definitions"' in prompt
        assert '- node-1.1: "Key Terms"' in prompt
        assert '- node-2: "Procedures"' in prompt
        assert '- node-3: "Restrictions"' in prompt

    @pytest.mark.asyncio
    async def test_structure_tree_before_document_content(self):
        """Structure tree nodes appear before the DOCUMENT CONTENT section."""
        mock_client = _make_mock_llm_client(json.dumps({"relations": []}))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()
        index = _make_index_result()

        await analyzer.analyze(ir, language="es", index_result=index)

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        tree_pos = prompt.index("--- STRUCTURE TREE NODES ---")
        doc_pos = prompt.index("--- DOCUMENT CONTENT ---")
        assert tree_pos < doc_pos

    @pytest.mark.asyncio
    async def test_without_index_no_structure_section(self):
        """When index_result is None, no structure tree section is in the prompt."""
        mock_client = _make_mock_llm_client(json.dumps({"relations": []}))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es", index_result=None)

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "--- STRUCTURE TREE NODES ---" not in prompt


class TestRelationsAnalyzerFailures:
    """Tests for error scenarios."""

    @pytest.mark.asyncio
    async def test_invalid_json_raises_error(self):
        """Non-JSON LLM response raises RelationsAnalysisError."""
        mock_client = _make_mock_llm_client("This is not JSON at all.")
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(RelationsAnalysisError, match="not valid JSON"):
            await analyzer.analyze(ir, language="es")

    @pytest.mark.asyncio
    async def test_invalid_schema_raises_error(self):
        """Valid JSON that doesn't match RelationsResult schema raises error."""
        # Missing required 'relations' field
        mock_client = _make_mock_llm_client(json.dumps({"items": []}))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(
            RelationsAnalysisError, match="does not match RelationsResult schema"
        ):
            await analyzer.analyze(ir, language="es")

    @pytest.mark.asyncio
    async def test_invalid_relation_type_raises_error(self):
        """A relation with an invalid type raises RelationsAnalysisError.

        Pydantic's Literal type on SectionRelation.type enforces the vocabulary,
        so invalid types are caught during model_validate as a schema error.
        """
        data = {
            "relations": [
                {
                    "source_section": "A",
                    "target_section": "B",
                    "type": "follows",  # invalid type
                    "description": "Section A follows B",
                    "source_ref": None,
                }
            ]
        }
        mock_client = _make_mock_llm_client(json.dumps(data))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(
            RelationsAnalysisError, match="does not match RelationsResult schema"
        ):
            await analyzer.analyze(ir, language="es")

    @pytest.mark.asyncio
    async def test_timeout_raises_asyncio_timeout(self):
        """LLM call exceeding 30s raises asyncio.TimeoutError."""
        mock_client = MagicMock()

        async def slow_call(*args, **kwargs):
            await asyncio.sleep(60)
            return LLMResponse(content="{}", model_id="test")

        mock_client.call = slow_call
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(asyncio.TimeoutError):
            await analyzer.analyze(ir, language="es")

    @pytest.mark.asyncio
    async def test_llm_exception_propagates(self):
        """Exceptions from LLMClient.call propagate to the caller."""
        mock_client = MagicMock()
        mock_client.call = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(RuntimeError, match="LLM unavailable"):
            await analyzer.analyze(ir, language="es")

    @pytest.mark.asyncio
    async def test_multiple_invalid_types_reported(self):
        """Multiple invalid relation types are caught by schema validation."""
        data = {
            "relations": [
                {
                    "source_section": "A",
                    "target_section": "B",
                    "type": "follows",
                    "description": "test",
                    "source_ref": None,
                },
                {
                    "source_section": "C",
                    "target_section": "D",
                    "type": "precedes",
                    "description": "test",
                    "source_ref": None,
                },
            ]
        }
        mock_client = _make_mock_llm_client(json.dumps(data))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        with pytest.raises(
            RelationsAnalysisError, match="does not match RelationsResult schema"
        ):
            await analyzer.analyze(ir, language="es")
