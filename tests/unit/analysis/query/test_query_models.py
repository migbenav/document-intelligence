"""Unit tests for the Natural Language Query Pydantic models.

Verifies validation constraints, defaults, and serialization round-trips
for all models defined in app.models.query.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.query import (
    QueryContextElement,
    QueryContextRelation,
    QueryContext,
    QueryErrorResponse,
    QueryMetadata,
    QueryRequest,
    QueryResponse,
    QuerySourceRef,
)


# --- Fixtures ---


@pytest.fixture
def sample_metadata() -> QueryMetadata:
    return QueryMetadata(
        prompt_version="query-answering-v1",
        model_id="gemini/gemini-2.5-flash",
        temperature=0.1,
        timestamp=datetime(2026, 8, 1, 14, 30, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_source_ref() -> QuerySourceRef:
    return QuerySourceRef(
        document_id="doc-001",
        chunk_id="chunk-005",
        page=None,
        section="## Actors and Roles",
        evidence="The System Administrator is responsible for infrastructure management",
        evidence_verified=True,
    )


@pytest.fixture
def sample_response(sample_metadata: QueryMetadata, sample_source_ref: QuerySourceRef) -> QueryResponse:
    return QueryResponse(
        answer="The document describes the System Administrator role.",
        answerable=True,
        source_refs=[sample_source_ref],
        all_evidence_unverified=False,
        metadata=sample_metadata,
    )


# --- QueryRequest Tests ---


class TestQueryRequest:
    def test_valid_question(self):
        req = QueryRequest(question="What are the main actors?")
        assert req.question == "What are the main actors?"

    def test_question_min_length_1(self):
        """Question must be at least 1 character (Req 1.8, 5.4)."""
        # Single character is valid
        req = QueryRequest(question="?")
        assert req.question == "?"

        # Empty string fails
        with pytest.raises(ValidationError) as exc_info:
            QueryRequest(question="")
        assert "question" in str(exc_info.value).lower()

    def test_question_max_length_1000(self):
        """Question must be at most 1000 characters (Req 1.8, 5.4)."""
        # Exactly 1000 is valid
        req = QueryRequest(question="x" * 1000)
        assert len(req.question) == 1000

        # 1001 fails
        with pytest.raises(ValidationError) as exc_info:
            QueryRequest(question="x" * 1001)
        assert "question" in str(exc_info.value).lower()

    def test_json_round_trip(self):
        req = QueryRequest(question="What is the document about?")
        json_str = req.model_dump_json()
        restored = QueryRequest.model_validate_json(json_str)
        assert restored == req


# --- QuerySourceRef Tests ---


class TestQuerySourceRef:
    def test_serialization_with_all_fields(self, sample_source_ref: QuerySourceRef):
        data = sample_source_ref.model_dump()
        assert data["document_id"] == "doc-001"
        assert data["chunk_id"] == "chunk-005"
        assert data["page"] is None
        assert data["section"] == "## Actors and Roles"
        assert data["evidence"] == "The System Administrator is responsible for infrastructure management"
        assert data["evidence_verified"] is True

    def test_page_and_section_optional(self):
        ref = QuerySourceRef(
            document_id="doc-001",
            chunk_id="chunk-001",
            evidence="Some evidence text",
        )
        assert ref.page is None
        assert ref.section is None

    def test_evidence_verified_defaults_false(self):
        """evidence_verified defaults to False (Req 4.1)."""
        ref = QuerySourceRef(
            document_id="doc-001",
            chunk_id="chunk-001",
            evidence="Some text",
        )
        assert ref.evidence_verified is False

    def test_evidence_max_length_500(self):
        """Evidence text span is limited to 500 characters (Req 3.5)."""
        # Exactly 500 is valid
        ref = QuerySourceRef(
            document_id="doc-001",
            chunk_id="chunk-001",
            evidence="e" * 500,
        )
        assert len(ref.evidence) == 500

        # 501 fails
        with pytest.raises(ValidationError) as exc_info:
            QuerySourceRef(
                document_id="doc-001",
                chunk_id="chunk-001",
                evidence="e" * 501,
            )
        assert "evidence" in str(exc_info.value).lower()

    def test_evidence_required(self):
        with pytest.raises(ValidationError):
            QuerySourceRef(
                document_id="doc-001",
                chunk_id="chunk-001",
            )

    def test_json_round_trip(self, sample_source_ref: QuerySourceRef):
        json_str = sample_source_ref.model_dump_json()
        restored = QuerySourceRef.model_validate_json(json_str)
        assert restored == sample_source_ref


# --- QueryMetadata Tests ---


class TestQueryMetadata:
    def test_serialization(self, sample_metadata: QueryMetadata):
        data = sample_metadata.model_dump()
        assert data["prompt_version"] == "query-answering-v1"
        assert data["model_id"] == "gemini/gemini-2.5-flash"
        assert data["temperature"] == 0.1
        assert data["timestamp"] == datetime(2026, 8, 1, 14, 30, 0, tzinfo=timezone.utc)

    def test_timestamp_serialization_json(self, sample_metadata: QueryMetadata):
        data = sample_metadata.model_dump(mode="json")
        assert "2026-08-01" in data["timestamp"]

    def test_all_fields_required(self):
        with pytest.raises(ValidationError):
            QueryMetadata(
                prompt_version="v1",
                model_id="model",
                # missing temperature and timestamp
            )

    def test_json_round_trip(self, sample_metadata: QueryMetadata):
        json_str = sample_metadata.model_dump_json()
        restored = QueryMetadata.model_validate_json(json_str)
        assert restored == sample_metadata


# --- QueryResponse Tests ---


class TestQueryResponse:
    def test_answer_max_length_5000(self, sample_metadata: QueryMetadata, sample_source_ref: QuerySourceRef):
        """Answer text limited to 5000 characters (Req 5.1)."""
        # Exactly 5000 is valid
        resp = QueryResponse(
            answer="a" * 5000,
            answerable=True,
            source_refs=[sample_source_ref],
            metadata=sample_metadata,
        )
        assert len(resp.answer) == 5000

        # 5001 fails
        with pytest.raises(ValidationError) as exc_info:
            QueryResponse(
                answer="a" * 5001,
                answerable=True,
                source_refs=[sample_source_ref],
                metadata=sample_metadata,
            )
        assert "answer" in str(exc_info.value).lower()

    def test_source_refs_max_10(self, sample_metadata: QueryMetadata):
        """source_refs limited to max 10 (Req 5.1)."""
        refs = [
            QuerySourceRef(
                document_id="doc-001",
                chunk_id=f"chunk-{i:03d}",
                evidence=f"Evidence number {i}",
            )
            for i in range(10)
        ]
        # Exactly 10 is valid
        resp = QueryResponse(
            answer="The answer.",
            answerable=True,
            source_refs=refs,
            metadata=sample_metadata,
        )
        assert len(resp.source_refs) == 10

        # 11 fails
        refs_11 = refs + [
            QuerySourceRef(
                document_id="doc-001",
                chunk_id="chunk-010",
                evidence="One too many",
            )
        ]
        with pytest.raises(ValidationError) as exc_info:
            QueryResponse(
                answer="The answer.",
                answerable=True,
                source_refs=refs_11,
                metadata=sample_metadata,
            )
        assert "source_refs" in str(exc_info.value).lower()

    def test_all_evidence_unverified_defaults_false(self, sample_metadata: QueryMetadata):
        """all_evidence_unverified defaults to False (Req 4.5)."""
        resp = QueryResponse(
            answer="Cannot answer.",
            answerable=False,
            metadata=sample_metadata,
        )
        assert resp.all_evidence_unverified is False

    def test_source_refs_defaults_empty(self, sample_metadata: QueryMetadata):
        """source_refs defaults to empty list."""
        resp = QueryResponse(
            answer="Cannot answer this question.",
            answerable=False,
            metadata=sample_metadata,
        )
        assert resp.source_refs == []

    def test_cannot_answer_response(self, sample_metadata: QueryMetadata):
        """A valid cannot-answer response with answerable=False and empty refs."""
        resp = QueryResponse(
            answer="The available knowledge does not contain information about deployment.",
            answerable=False,
            source_refs=[],
            all_evidence_unverified=False,
            metadata=sample_metadata,
        )
        assert resp.answerable is False
        assert resp.source_refs == []

    def test_full_serialization(self, sample_response: QueryResponse):
        data = sample_response.model_dump()
        assert data["answerable"] is True
        assert len(data["source_refs"]) == 1
        assert data["source_refs"][0]["document_id"] == "doc-001"
        assert data["metadata"]["prompt_version"] == "query-answering-v1"

    def test_json_round_trip(self, sample_response: QueryResponse):
        json_str = sample_response.model_dump_json()
        restored = QueryResponse.model_validate_json(json_str)
        assert restored == sample_response


# --- QueryErrorResponse Tests ---


class TestQueryErrorResponse:
    def test_basic_error(self):
        err = QueryErrorResponse(
            error="query_failed",
            message="LLM service unavailable.",
        )
        assert err.error == "query_failed"
        assert err.message == "LLM service unavailable."
        assert err.question is None

    def test_parse_error_with_question(self):
        err = QueryErrorResponse(
            error="response_parse_error",
            message="Failed to parse LLM response.",
            question="What are the main actors?",
        )
        assert err.error == "response_parse_error"
        assert err.question == "What are the main actors?"

    def test_question_field_optional(self):
        err = QueryErrorResponse(
            error="km_not_completed",
            message="Queries require a completed Knowledge Model.",
        )
        assert err.question is None

    def test_json_round_trip(self):
        err = QueryErrorResponse(
            error="not_found",
            message="Document not found.",
            question="Some question",
        )
        json_str = err.model_dump_json()
        restored = QueryErrorResponse.model_validate_json(json_str)
        assert restored == err


# --- QueryContextElement Tests ---


class TestQueryContextElement:
    def test_valid_element(self):
        elem = QueryContextElement(
            element_id="elem-001",
            type="concepto",
            name="System Administrator",
            content="Manages infrastructure and user provisioning",
            evidence="The System Administrator manages the infrastructure",
            verified=True,
        )
        assert elem.element_id == "elem-001"
        assert elem.type == "concepto"
        assert elem.verified is True

    def test_all_fields_required(self):
        with pytest.raises(ValidationError):
            QueryContextElement(
                element_id="elem-001",
                type="concepto",
                # missing name, content, evidence, verified
            )

    def test_json_round_trip(self):
        elem = QueryContextElement(
            element_id="elem-002",
            type="restriccion",
            name="Response Time",
            content="All endpoints respond in 200ms",
            evidence="All API endpoints must respond within 200ms",
            verified=False,
        )
        json_str = elem.model_dump_json()
        restored = QueryContextElement.model_validate_json(json_str)
        assert restored == elem


# --- QueryContextRelation Tests ---


class TestQueryContextRelation:
    def test_valid_relation(self):
        rel = QueryContextRelation(
            source_id="elem-001",
            target_id="elem-002",
            type="constrains",
        )
        assert rel.source_id == "elem-001"
        assert rel.target_id == "elem-002"
        assert rel.type == "constrains"
        assert rel.description is None

    def test_description_optional(self):
        rel = QueryContextRelation(
            source_id="elem-001",
            target_id="elem-003",
            type="depends_on",
            description="Requires the authentication module",
        )
        assert rel.description == "Requires the authentication module"

    def test_json_round_trip(self):
        rel = QueryContextRelation(
            source_id="elem-005",
            target_id="elem-010",
            type="participates_in",
            description="Actor participates in the process",
        )
        json_str = rel.model_dump_json()
        restored = QueryContextRelation.model_validate_json(json_str)
        assert restored == rel


# --- QueryContext Tests ---


class TestQueryContext:
    def test_valid_context(self):
        ctx = QueryContext(
            elements=[
                QueryContextElement(
                    element_id="elem-001",
                    type="concepto",
                    name="Admin",
                    content="Administrator",
                    evidence="Admin manages system",
                    verified=True,
                )
            ],
            relations=[
                QueryContextRelation(
                    source_id="elem-001",
                    target_id="elem-002",
                    type="constrains",
                )
            ],
            total_tokens=500,
            has_unverified_elements=False,
        )
        assert len(ctx.elements) == 1
        assert len(ctx.relations) == 1
        assert ctx.total_tokens == 500
        assert ctx.has_unverified_elements is False

    def test_defaults_empty_lists(self):
        ctx = QueryContext(
            total_tokens=0,
            has_unverified_elements=False,
        )
        assert ctx.elements == []
        assert ctx.relations == []

    def test_json_round_trip(self):
        ctx = QueryContext(
            elements=[
                QueryContextElement(
                    element_id="elem-001",
                    type="actor",
                    name="User",
                    content="End user of the system",
                    evidence="Users interact with the product",
                    verified=True,
                )
            ],
            relations=[],
            total_tokens=120,
            has_unverified_elements=False,
        )
        json_str = ctx.model_dump_json()
        restored = QueryContext.model_validate_json(json_str)
        assert restored == ctx
