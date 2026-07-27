"""Backward compatibility tests for Analysis Quality v2.

Verifies that existing v1 analysis results (without new v2 fields) still
load, parse, and function correctly after the model extensions.

New optional fields (functional_group, coherence_note, domain, etc.) must
default gracefully when absent from stored data.

Requirements: Design Decision 1 (backward compat), Property 4
"""

from datetime import datetime, timezone

import pytest

from app.analysis.on_demand.models import (
    AnalysisRecord,
    AnalysisStatus,
    AnalysisType,
    AnsweredQuestion,
    ConclusionsResult,
    IndexResult,
    Observation,
    QuestionsResult,
    RelationsResult,
    SectionRelation,
    SourceRef,
    StructureNode,
)


# --- V1 JSON Payloads (simulating stored data without v2 fields) ---


def _v1_index_result_dict() -> dict:
    """A v1-style IndexResult: no functional_group, no original_headings, no document_purpose."""
    return {
        "tree": [
            {
                "id": "n1",
                "title": "Capítulo 1 - Introducción",
                "level": 1,
                "role": "describes",
                "question_answered": "What does the introduction cover?",
                "source_ref": {
                    "chunk_ids": ["c1", "c2"],
                    "text_excerpt": "Este documento describe...",
                    "section": "Introducción",
                },
                "children": [
                    {
                        "id": "n1-1",
                        "title": "1.1 Alcance",
                        "level": 2,
                        "role": "defines",
                        "question_answered": None,
                        "source_ref": None,
                        "children": [],
                    }
                ],
            },
            {
                "id": "n2",
                "title": "Capítulo 2 - Reglas",
                "level": 1,
                "role": "regulates",
                "question_answered": "What rules are established?",
                "source_ref": None,
                "children": [],
            },
        ]
    }


def _v1_questions_result_dict() -> dict:
    """A v1-style QuestionsResult: no coherence_note field."""
    return {
        "document_questions": [
            {
                "question": "¿Cuál es el propósito del documento?",
                "level": "document",
                "section_title": None,
                "source_ref": {
                    "chunk_ids": ["c1"],
                    "text_excerpt": "El propósito de este reglamento...",
                    "section": "Introducción",
                },
            },
            {
                "question": "¿Qué regula este documento?",
                "level": "document",
                "section_title": None,
                "source_ref": None,
            },
        ],
        "section_questions": [
            {
                "question": "¿Quién aprueba los gastos?",
                "level": "section",
                "section_title": "Capítulo 3",
                "source_ref": None,
            },
        ],
    }


def _v1_conclusions_result_dict() -> dict:
    """A v1-style ConclusionsResult: no domain, no domains_identified, v1 categories."""
    return {
        "observations": [
            {
                "category": "coherence",
                "description": "The document lacks a clear structure.",
                "suggestion": "Reorganize chapters by theme.",
                "section_ref": "Capítulo 2",
                "source_ref": {
                    "chunk_ids": ["c5"],
                    "text_excerpt": "Los artículos sobre estacionamiento...",
                    "section": "Capítulo 2",
                },
            },
            {
                "category": "reordering",
                "description": "Chapter 5 should come before Chapter 3.",
                "suggestion": "Move Chapter 5 before Chapter 3.",
                "section_ref": "Capítulo 5",
                "source_ref": None,
            },
            {
                "category": "duplication",
                "description": "Content in 2.1 repeats 4.3.",
                "suggestion": "Remove duplication from 2.1.",
                "section_ref": "2.1, 4.3",
                "source_ref": None,
            },
        ]
    }


def _v1_relations_result_dict() -> dict:
    """A v1-style RelationsResult: v1 types (constrains, depends_on, complements), no domain."""
    return {
        "relations": [
            {
                "source_section": "Capítulo 1",
                "target_section": "Capítulo 3",
                "type": "depends_on",
                "description": "Chapter 3 uses definitions from Chapter 1.",
                "source_ref": {
                    "chunk_ids": ["c3"],
                    "text_excerpt": "Como se define en el Capítulo 1...",
                    "section": None,
                },
            },
            {
                "source_section": "Sección 2.1",
                "target_section": "Sección 2.3",
                "type": "contradicts",
                "description": "These sections state conflicting requirements.",
                "source_ref": None,
            },
            {
                "source_section": "Apéndice A",
                "target_section": "Capítulo 2",
                "type": "complements",
                "description": "Appendix provides data tables for Chapter 2.",
                "source_ref": None,
            },
        ]
    }


def _v1_analysis_record_dict(analysis_type: str, result: dict) -> dict:
    """Build a v1-style AnalysisRecord dict (no requested_model, no fallback_used)."""
    return {
        "id": "rec-v1-001",
        "document_id": "doc-001",
        "analysis_type": analysis_type,
        "status": "completed",
        "result": result,
        "model_id": "gemini/gemini-2.5-flash",
        "prompt_version": "build-index-v1",
        "error_message": None,
        "created_at": "2025-06-15T10:00:00Z",
        "updated_at": "2025-06-15T10:01:00Z",
    }


# --- Test Classes ---


class TestIndexResultBackwardCompat:
    """Verify v1 IndexResult (without v2 fields) still parses correctly."""

    def test_v1_index_result_loads_without_v2_fields(self):
        """IndexResult from v1 JSON (no functional_group, no original_headings, no document_purpose) parses."""
        data = _v1_index_result_dict()
        result = IndexResult.model_validate(data)

        assert len(result.tree) == 2
        assert result.tree[0].id == "n1"
        assert result.tree[0].title == "Capítulo 1 - Introducción"
        assert result.document_purpose is None

    def test_v1_structure_node_has_default_v2_fields(self):
        """StructureNode from v1 data defaults functional_group=None and original_headings=[]."""
        data = _v1_index_result_dict()
        result = IndexResult.model_validate(data)
        node = result.tree[0]

        assert node.functional_group is None
        assert node.original_headings == []

    def test_v1_structure_node_children_have_default_v2_fields(self):
        """Child nodes from v1 data also default v2 fields."""
        data = _v1_index_result_dict()
        result = IndexResult.model_validate(data)
        child = result.tree[0].children[0]

        assert child.functional_group is None
        assert child.original_headings == []

    def test_v1_index_result_serializes_back_with_v2_defaults(self):
        """Serializing a parsed v1 IndexResult includes v2 fields with defaults."""
        data = _v1_index_result_dict()
        result = IndexResult.model_validate(data)
        serialized = result.model_dump()

        assert serialized["document_purpose"] is None
        assert serialized["tree"][0]["functional_group"] is None
        assert serialized["tree"][0]["original_headings"] == []

    def test_v1_role_values_still_accepted(self):
        """v1 role values (describes, defines, regulates, etc.) still parse."""
        v1_roles = ["describes", "defines", "regulates", "establishes", "classifies", "lists", "recommends"]
        for role in v1_roles:
            node = StructureNode(id="test", title="Test", level=1, role=role)
            assert node.role == role


class TestQuestionsResultBackwardCompat:
    """Verify v1 QuestionsResult (without coherence_note) still parses correctly."""

    def test_v1_questions_result_loads_without_coherence_note(self):
        """QuestionsResult from v1 JSON (no coherence_note) parses successfully."""
        data = _v1_questions_result_dict()
        result = QuestionsResult.model_validate(data)

        assert len(result.document_questions) == 2
        assert len(result.section_questions) == 1
        assert result.coherence_note is None

    def test_v1_questions_preserve_source_refs(self):
        """Source refs from v1 questions data are preserved."""
        data = _v1_questions_result_dict()
        result = QuestionsResult.model_validate(data)

        assert result.document_questions[0].source_ref is not None
        assert result.document_questions[0].source_ref.text_excerpt == "El propósito de este reglamento..."

    def test_v1_questions_null_source_refs_accepted(self):
        """Questions with null source_ref still parse."""
        data = _v1_questions_result_dict()
        result = QuestionsResult.model_validate(data)

        assert result.document_questions[1].source_ref is None
        assert result.section_questions[0].source_ref is None


class TestConclusionsResultBackwardCompat:
    """Verify v1 ConclusionsResult (without domain, without domains_identified) still parses."""

    def test_v1_conclusions_result_loads_without_v2_fields(self):
        """ConclusionsResult from v1 JSON (no domain, no domains_identified) parses."""
        data = _v1_conclusions_result_dict()
        result = ConclusionsResult.model_validate(data)

        assert len(result.observations) == 3
        assert result.domains_identified == []

    def test_v1_observation_categories_still_valid(self):
        """v1 categories (coherence, reordering, duplication, orphan, missing) still accepted."""
        data = _v1_conclusions_result_dict()
        result = ConclusionsResult.model_validate(data)

        categories = [obs.category for obs in result.observations]
        assert "coherence" in categories
        assert "reordering" in categories
        assert "duplication" in categories

    def test_v1_observation_domain_defaults_to_none(self):
        """Observations from v1 data default domain=None."""
        data = _v1_conclusions_result_dict()
        result = ConclusionsResult.model_validate(data)

        for obs in result.observations:
            assert obs.domain is None

    def test_v1_orphan_and_missing_categories_still_valid(self):
        """v1-only categories 'orphan' and 'missing' still parse."""
        obs_orphan = Observation(
            category="orphan",
            description="Section has no parent.",
            suggestion="Move to appropriate chapter.",
        )
        obs_missing = Observation(
            category="missing",
            description="Expected section is absent.",
            suggestion="Add a conclusions section.",
        )
        assert obs_orphan.category == "orphan"
        assert obs_missing.category == "missing"


class TestRelationsResultBackwardCompat:
    """Verify v1 RelationsResult (v1 types, no domain) still parses."""

    def test_v1_relations_result_loads_with_legacy_types(self):
        """RelationsResult with v1 types (constrains, depends_on, complements) parses."""
        data = _v1_relations_result_dict()
        result = RelationsResult.model_validate(data)

        assert len(result.relations) == 3
        types = [r.type for r in result.relations]
        assert "depends_on" in types
        assert "contradicts" in types
        assert "complements" in types

    def test_v1_relation_domain_defaults_to_none(self):
        """Relations from v1 data default domain=None."""
        data = _v1_relations_result_dict()
        result = RelationsResult.model_validate(data)

        for rel in result.relations:
            assert rel.domain is None

    def test_v1_constrains_type_still_accepted(self):
        """The v1 'constrains' type is still in the allowed Literal values."""
        rel = SectionRelation(
            source_section="A",
            target_section="B",
            type="constrains",
            description="A constrains B.",
        )
        assert rel.type == "constrains"


class TestAnalysisRecordBackwardCompat:
    """Verify v1 AnalysisRecord (without requested_model, fallback_used) still loads."""

    def test_v1_record_loads_without_v2_fields(self):
        """AnalysisRecord from v1 JSON (no requested_model, no fallback_used) parses."""
        data = _v1_analysis_record_dict("build_index", _v1_index_result_dict())
        record = AnalysisRecord.model_validate(data)

        assert record.id == "rec-v1-001"
        assert record.analysis_type == AnalysisType.BUILD_INDEX
        assert record.status == AnalysisStatus.COMPLETED
        assert record.model_id == "gemini/gemini-2.5-flash"
        assert record.prompt_version == "build-index-v1"

    def test_v1_record_defaults_requested_model_to_none(self):
        """requested_model defaults to None when absent from v1 data."""
        data = _v1_analysis_record_dict("questions_answered", _v1_questions_result_dict())
        record = AnalysisRecord.model_validate(data)

        assert record.requested_model is None

    def test_v1_record_defaults_fallback_used_to_false(self):
        """fallback_used defaults to False when absent from v1 data."""
        data = _v1_analysis_record_dict("conclusions", _v1_conclusions_result_dict())
        record = AnalysisRecord.model_validate(data)

        assert record.fallback_used is False

    def test_v1_record_round_trip_preserves_result(self):
        """Round-trip (parse → serialize → parse) preserves v1 result data."""
        original_data = _v1_analysis_record_dict("section_relations", _v1_relations_result_dict())
        record = AnalysisRecord.model_validate(original_data)

        # Serialize and re-parse
        json_str = record.model_dump_json()
        restored = AnalysisRecord.model_validate_json(json_str)

        assert restored.result == record.result
        assert restored.model_id == record.model_id
        assert restored.analysis_type == record.analysis_type

    def test_v1_record_with_failed_status_and_no_result(self):
        """A failed v1 record with null result parses correctly."""
        data = {
            "id": "rec-v1-fail",
            "document_id": "doc-002",
            "analysis_type": "build_index",
            "status": "failed",
            "result": None,
            "model_id": None,
            "prompt_version": None,
            "error_message": "LLM call failed",
            "created_at": "2025-06-15T10:00:00Z",
            "updated_at": "2025-06-15T10:00:05Z",
        }
        record = AnalysisRecord.model_validate(data)

        assert record.status == AnalysisStatus.FAILED
        assert record.result is None
        assert record.error_message == "LLM call failed"
        assert record.requested_model is None
        assert record.fallback_used is False

    @pytest.mark.parametrize("analysis_type", [
        "build_index",
        "section_relations",
        "questions_answered",
        "conclusions",
    ])
    def test_v1_record_all_analysis_types_parse(self, analysis_type):
        """v1 records for all four analysis types parse without error."""
        result_map = {
            "build_index": _v1_index_result_dict(),
            "section_relations": _v1_relations_result_dict(),
            "questions_answered": _v1_questions_result_dict(),
            "conclusions": _v1_conclusions_result_dict(),
        }
        data = _v1_analysis_record_dict(analysis_type, result_map[analysis_type])
        record = AnalysisRecord.model_validate(data)

        assert record.analysis_type.value == analysis_type
        assert record.result is not None


class TestMixedV1V2Data:
    """Verify that partially-populated data (some v2 fields present, some absent) works."""

    def test_index_node_with_functional_group_but_no_original_headings(self):
        """A node can have functional_group set but original_headings defaults to []."""
        node = StructureNode(
            id="n1",
            title="Ejecución",
            level=1,
            role="enables",
            functional_group="Ejecución operativa",
        )
        assert node.functional_group == "Ejecución operativa"
        assert node.original_headings == []

    def test_index_result_with_purpose_but_v1_nodes(self):
        """IndexResult can have document_purpose set even if nodes lack v2 fields."""
        data = _v1_index_result_dict()
        data["document_purpose"] = "This document regulates building management."
        result = IndexResult.model_validate(data)

        assert result.document_purpose == "This document regulates building management."
        assert result.tree[0].functional_group is None

    def test_conclusions_with_some_domains_some_without(self):
        """Observations can mix domain-tagged and domain-less entries."""
        data = {
            "observations": [
                {
                    "category": "purpose_mismatch",
                    "description": "Procedural content in normative section.",
                    "suggestion": "Move to procedures chapter.",
                    "section_ref": "Art. 5",
                    "domain": "parking",
                    "source_ref": None,
                },
                {
                    "category": "coherence",
                    "description": "Legacy observation without domain.",
                    "suggestion": "Reorganize.",
                    "section_ref": None,
                    "source_ref": None,
                },
            ],
            "domains_identified": ["parking"],
        }
        result = ConclusionsResult.model_validate(data)

        assert result.observations[0].domain == "parking"
        assert result.observations[1].domain is None
        assert result.domains_identified == ["parking"]

    def test_relation_v2_type_with_domain(self):
        """v2 relation types (enables, restricts, requires, implements) work with domain."""
        rel = SectionRelation(
            source_section="Art. 10",
            target_section="Art. 15",
            type="enables",
            description="Art. 10 enables the procedures in Art. 15.",
            domain="operations",
        )
        assert rel.type == "enables"
        assert rel.domain == "operations"

    def test_relation_v1_type_without_domain(self):
        """v1 relation types (constrains, depends_on, complements) still work without domain."""
        rel = SectionRelation(
            source_section="Ch.1",
            target_section="Ch.3",
            type="constrains",
            description="Chapter 1 constrains Chapter 3.",
        )
        assert rel.type == "constrains"
        assert rel.domain is None
