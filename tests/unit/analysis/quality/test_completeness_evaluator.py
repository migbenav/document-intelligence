"""Unit tests for the CompletenessEvaluator.

Tests cover:
- Generic type returns empty list (Req 3.3)
- Missing elements detected when KM lacks schema-expected elements (Req 3.1, 3.2)
- Partial coverage assessment via LLM (Req 3.5)
- Empty KM raises error (Req 3.6)
- Schema not found raises error (Req 10.4)

Requirements validated: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 8.3, 10.4, 10.5
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.analysis.llm_client import LLMClient, LLMResponse
from app.analysis.quality.completeness_evaluator import (
    CompletenessEvaluationError,
    CompletenessEvaluator,
)
from app.models.knowledge_model import (
    ExtractionMetadata,
    KnowledgeElement,
    KnowledgeModel,
    SourceRef,
)


# --- Fixtures ---


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create a mock LLMClient with async call method."""
    client = MagicMock(spec=LLMClient)
    client.call = AsyncMock()
    return client


@pytest.fixture
def sample_source_ref() -> SourceRef:
    return SourceRef(
        document_id="doc-001",
        chunk_id="chunk-001",
        page=1,
        section="## Introduction",
        evidence="Sample evidence text",
    )


@pytest.fixture
def sample_metadata() -> ExtractionMetadata:
    return ExtractionMetadata(
        prompt_version="extraction-v1",
        model_id="gemini/gemini-2.5-flash-preview-05-20",
        temperature=0.1,
        element_count=3,
        relationship_count=1,
        verification_rate=0.8,
        extracted_at=datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def empty_km(sample_metadata: ExtractionMetadata) -> KnowledgeModel:
    """KnowledgeModel with zero elements."""
    return KnowledgeModel(
        document_id="doc-001",
        document_type="prd",
        elements=[],
        extraction_metadata=sample_metadata,
    )


@pytest.fixture
def prd_km_with_all_elements(
    sample_source_ref: SourceRef, sample_metadata: ExtractionMetadata
) -> KnowledgeModel:
    """KnowledgeModel for a PRD with all expected elements present."""
    elements = [
        KnowledgeElement(
            id="elem-001",
            type="proposito",
            name="Propósito del producto",
            content="The product aims to provide document analysis.",
            source_ref=sample_source_ref,
            verified=True,
        ),
        KnowledgeElement(
            id="elem-002",
            type="actor",
            name="Usuarios principales",
            content="Technical writers and product managers.",
            source_ref=sample_source_ref,
            verified=True,
        ),
        KnowledgeElement(
            id="elem-003",
            type="regla",
            name="Requisitos funcionales del sistema",
            content="The system must extract knowledge and detect inconsistencies.",
            source_ref=sample_source_ref,
            verified=True,
        ),
        KnowledgeElement(
            id="elem-004",
            type="restriccion",
            name="Restricciones técnicas",
            content="Must use Python backend with FastAPI.",
            source_ref=sample_source_ref,
            verified=True,
        ),
        KnowledgeElement(
            id="elem-005",
            type="regla",
            name="Criterios de éxito",
            content="80% user satisfaction rate.",
            source_ref=sample_source_ref,
            verified=True,
        ),
    ]
    return KnowledgeModel(
        document_id="doc-001",
        document_type="prd",
        elements=elements,
        extraction_metadata=sample_metadata,
    )


@pytest.fixture
def prd_km_missing_elements(
    sample_source_ref: SourceRef, sample_metadata: ExtractionMetadata
) -> KnowledgeModel:
    """KnowledgeModel for a PRD with some elements missing."""
    elements = [
        KnowledgeElement(
            id="elem-001",
            type="proposito",
            name="Propósito del documento",
            content="This document defines the product requirements.",
            source_ref=sample_source_ref,
            verified=True,
        ),
        KnowledgeElement(
            id="elem-002",
            type="actor",
            name="Usuarios del sistema",
            content="Developers and QA engineers.",
            source_ref=sample_source_ref,
            verified=True,
        ),
    ]
    return KnowledgeModel(
        document_id="doc-001",
        document_type="prd",
        elements=elements,
        extraction_metadata=sample_metadata,
    )


@pytest.fixture
def evaluator(mock_llm_client: MagicMock) -> CompletenessEvaluator:
    return CompletenessEvaluator(mock_llm_client)


# --- Tests: Generic Type Returns Empty (Req 3.3) ---


class TestGenericTypeSkip:
    @pytest.mark.asyncio
    async def test_generic_type_returns_empty_list(
        self, evaluator: CompletenessEvaluator, prd_km_with_all_elements: KnowledgeModel
    ):
        """Generic document type skips completeness evaluation entirely."""
        result = await evaluator.evaluate(prd_km_with_all_elements, "generic")
        assert result == []

    @pytest.mark.asyncio
    async def test_generic_type_does_not_call_llm(
        self,
        evaluator: CompletenessEvaluator,
        mock_llm_client: MagicMock,
        prd_km_with_all_elements: KnowledgeModel,
    ):
        """No LLM call is made when document type is generic."""
        await evaluator.evaluate(prd_km_with_all_elements, "generic")
        mock_llm_client.call.assert_not_called()


# --- Tests: Missing Elements Detected (Req 3.1, 3.2) ---


class TestMissingElementsDetection:
    @pytest.mark.asyncio
    async def test_missing_elements_detected_for_prd(
        self,
        evaluator: CompletenessEvaluator,
        mock_llm_client: MagicMock,
        prd_km_missing_elements: KnowledgeModel,
    ):
        """Elements absent from KM are reported as missing findings."""
        # Mock LLM response for partial coverage assessment of present elements
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"assessments": [
                {"expected_element_name": "propósito", "classification": "full", "description": "Adequate coverage", "severity": "high"},
                {"expected_element_name": "usuarios/actores", "classification": "full", "description": "Adequate coverage", "severity": "high"},
            ]}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        result = await evaluator.evaluate(prd_km_missing_elements, "prd")

        # Should find missing: requisitos funcionales, restricciones, criterios de éxito
        missing_findings = [f for f in result if f.classification == "missing"]
        assert len(missing_findings) == 3

        missing_names = {f.expected_element for f in missing_findings}
        assert "requisitos funcionales" in missing_names
        assert "restricciones" in missing_names
        assert "criterios de éxito" in missing_names

    @pytest.mark.asyncio
    async def test_missing_elements_have_correct_severity(
        self,
        evaluator: CompletenessEvaluator,
        mock_llm_client: MagicMock,
        prd_km_missing_elements: KnowledgeModel,
    ):
        """Missing element severity comes from schema importance."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"assessments": []}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        result = await evaluator.evaluate(prd_km_missing_elements, "prd")
        missing_findings = [f for f in result if f.classification == "missing"]

        # requisitos funcionales has importance "high" in PRD schema
        rf_finding = next(
            f for f in missing_findings if f.expected_element == "requisitos funcionales"
        )
        assert rf_finding.severity == "high"

        # restricciones has importance "medium" in PRD schema
        restr_finding = next(
            f for f in missing_findings if f.expected_element == "restricciones"
        )
        assert restr_finding.severity == "medium"

    @pytest.mark.asyncio
    async def test_missing_elements_have_schema_reference(
        self,
        evaluator: CompletenessEvaluator,
        mock_llm_client: MagicMock,
        prd_km_missing_elements: KnowledgeModel,
    ):
        """Missing element findings include the document type schema reference."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"assessments": []}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        result = await evaluator.evaluate(prd_km_missing_elements, "prd")
        missing_findings = [f for f in result if f.classification == "missing"]

        for finding in missing_findings:
            assert finding.schema_reference == "prd"

    @pytest.mark.asyncio
    async def test_no_missing_when_all_elements_present(
        self,
        evaluator: CompletenessEvaluator,
        mock_llm_client: MagicMock,
        prd_km_with_all_elements: KnowledgeModel,
    ):
        """When all expected elements are present, no 'missing' findings are produced."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"assessments": [
                {"expected_element_name": "propósito", "classification": "full", "description": "OK", "severity": "high"},
                {"expected_element_name": "usuarios/actores", "classification": "full", "description": "OK", "severity": "high"},
                {"expected_element_name": "requisitos funcionales", "classification": "full", "description": "OK", "severity": "high"},
                {"expected_element_name": "restricciones", "classification": "full", "description": "OK", "severity": "medium"},
                {"expected_element_name": "criterios de éxito", "classification": "full", "description": "OK", "severity": "medium"},
            ]}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        result = await evaluator.evaluate(prd_km_with_all_elements, "prd")
        missing_findings = [f for f in result if f.classification == "missing"]
        assert len(missing_findings) == 0


# --- Tests: Partial Coverage via LLM (Req 3.5) ---


class TestPartialCoverageAssessment:
    @pytest.mark.asyncio
    async def test_partial_elements_detected_from_llm(
        self,
        evaluator: CompletenessEvaluator,
        mock_llm_client: MagicMock,
        prd_km_with_all_elements: KnowledgeModel,
    ):
        """LLM classifying an element as partial produces a MissingElement finding."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"assessments": [
                {"expected_element_name": "propósito", "classification": "full", "description": "Adequate", "severity": "high"},
                {"expected_element_name": "usuarios/actores", "classification": "partial", "description": "Only mentions developers, missing other user types.", "severity": "high"},
                {"expected_element_name": "requisitos funcionales", "classification": "full", "description": "OK", "severity": "high"},
                {"expected_element_name": "restricciones", "classification": "full", "description": "OK", "severity": "medium"},
                {"expected_element_name": "criterios de éxito", "classification": "partial", "description": "Only mentions satisfaction rate, missing other KPIs.", "severity": "medium"},
            ]}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        result = await evaluator.evaluate(prd_km_with_all_elements, "prd")
        partial_findings = [f for f in result if f.classification == "partial"]

        assert len(partial_findings) == 2
        partial_names = {f.expected_element for f in partial_findings}
        assert "usuarios/actores" in partial_names
        assert "criterios de éxito" in partial_names

    @pytest.mark.asyncio
    async def test_partial_findings_include_description(
        self,
        evaluator: CompletenessEvaluator,
        mock_llm_client: MagicMock,
        prd_km_with_all_elements: KnowledgeModel,
    ):
        """Partial findings include the LLM's explanation of what's missing."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"assessments": [
                {"expected_element_name": "propósito", "classification": "partial", "description": "Only mentions goal, missing scope definition.", "severity": "high"},
                {"expected_element_name": "usuarios/actores", "classification": "full", "description": "OK", "severity": "high"},
                {"expected_element_name": "requisitos funcionales", "classification": "full", "description": "OK", "severity": "high"},
                {"expected_element_name": "restricciones", "classification": "full", "description": "OK", "severity": "medium"},
                {"expected_element_name": "criterios de éxito", "classification": "full", "description": "OK", "severity": "medium"},
            ]}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        result = await evaluator.evaluate(prd_km_with_all_elements, "prd")
        partial_findings = [f for f in result if f.classification == "partial"]

        assert len(partial_findings) == 1
        assert "Only mentions goal" in partial_findings[0].description

    @pytest.mark.asyncio
    async def test_llm_called_with_correct_prompt(
        self,
        evaluator: CompletenessEvaluator,
        mock_llm_client: MagicMock,
        prd_km_with_all_elements: KnowledgeModel,
    ):
        """LLM is called with primary tier and temperature 0.1."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"assessments": []}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        await evaluator.evaluate(prd_km_with_all_elements, "prd")

        mock_llm_client.call.assert_called_once()
        call_kwargs = mock_llm_client.call.call_args
        assert call_kwargs.kwargs["model_tier"] == "primary"
        assert call_kwargs.kwargs["temperature"] == 0.1

    @pytest.mark.asyncio
    async def test_invalid_llm_json_returns_no_partial_findings(
        self,
        evaluator: CompletenessEvaluator,
        mock_llm_client: MagicMock,
        prd_km_with_all_elements: KnowledgeModel,
    ):
        """If LLM returns invalid JSON, no partial findings are produced (graceful degradation)."""
        mock_llm_client.call.return_value = LLMResponse(
            content="This is not valid JSON",
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        result = await evaluator.evaluate(prd_km_with_all_elements, "prd")

        # No partial findings, but no missing either (all elements present)
        assert all(f.classification != "partial" for f in result)
        assert all(f.classification != "missing" for f in result)


# --- Tests: Empty KM Raises Error (Req 3.6) ---


class TestEmptyKnowledgeModel:
    @pytest.mark.asyncio
    async def test_empty_km_raises_error(
        self, evaluator: CompletenessEvaluator, empty_km: KnowledgeModel
    ):
        """Empty KM raises CompletenessEvaluationError."""
        with pytest.raises(CompletenessEvaluationError) as exc_info:
            await evaluator.evaluate(empty_km, "prd")
        assert "zero elements" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_empty_km_does_not_call_llm(
        self,
        evaluator: CompletenessEvaluator,
        mock_llm_client: MagicMock,
        empty_km: KnowledgeModel,
    ):
        """No LLM call when KM is empty."""
        with pytest.raises(CompletenessEvaluationError):
            await evaluator.evaluate(empty_km, "prd")
        mock_llm_client.call.assert_not_called()


# --- Tests: Schema Not Found Raises Error (Req 10.4) ---


class TestSchemaNotFound:
    @pytest.mark.asyncio
    async def test_unknown_type_raises_error(
        self,
        evaluator: CompletenessEvaluator,
        prd_km_with_all_elements: KnowledgeModel,
    ):
        """Unknown document type raises CompletenessEvaluationError."""
        with pytest.raises(CompletenessEvaluationError) as exc_info:
            await evaluator.evaluate(prd_km_with_all_elements, "unknown_type")
        assert "schema not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_empty_type_string_raises_error(
        self,
        evaluator: CompletenessEvaluator,
        prd_km_with_all_elements: KnowledgeModel,
    ):
        """Empty document type string raises CompletenessEvaluationError."""
        with pytest.raises(CompletenessEvaluationError) as exc_info:
            await evaluator.evaluate(prd_km_with_all_elements, "")
        assert "schema not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_schema_not_found_does_not_call_llm(
        self,
        evaluator: CompletenessEvaluator,
        mock_llm_client: MagicMock,
        prd_km_with_all_elements: KnowledgeModel,
    ):
        """No LLM call when schema is not found."""
        with pytest.raises(CompletenessEvaluationError):
            await evaluator.evaluate(prd_km_with_all_elements, "nonexistent_type")
        mock_llm_client.call.assert_not_called()
