"""Unit tests for document type schemas configuration.

Tests cover:
- All three document type schemas are defined (prd, technical_spec, policy_process)
- Generic type returns None
- Unknown types return None
- Schema structure is correct (each entry has name, description, importance)
- Importance values are valid (high, medium, low)

Requirements validated: 3.4, 10.4
"""

import pytest

from app.analysis.quality.schemas import DOCUMENT_TYPE_SCHEMAS, get_schema


# --- Schema Definition Tests (Req 3.4) ---


class TestSchemaDefinitions:
    def test_prd_schema_is_defined(self):
        """PRD schema exists in DOCUMENT_TYPE_SCHEMAS."""
        assert "prd" in DOCUMENT_TYPE_SCHEMAS

    def test_technical_spec_schema_is_defined(self):
        """Technical Spec schema exists in DOCUMENT_TYPE_SCHEMAS."""
        assert "technical_spec" in DOCUMENT_TYPE_SCHEMAS

    def test_policy_process_schema_is_defined(self):
        """Policy/Process schema exists in DOCUMENT_TYPE_SCHEMAS."""
        assert "policy_process" in DOCUMENT_TYPE_SCHEMAS

    def test_prd_schema_has_expected_elements(self):
        """PRD schema contains: propósito, usuarios/actores, requisitos funcionales, restricciones, criterios de éxito."""
        prd_names = [entry["name"] for entry in DOCUMENT_TYPE_SCHEMAS["prd"]]
        assert "propósito" in prd_names
        assert "usuarios/actores" in prd_names
        assert "requisitos funcionales" in prd_names
        assert "restricciones" in prd_names
        assert "criterios de éxito" in prd_names

    def test_technical_spec_schema_has_expected_elements(self):
        """Technical Spec schema contains: propósito, alcance, componentes/conceptos, interfaces, restricciones, decisiones."""
        ts_names = [entry["name"] for entry in DOCUMENT_TYPE_SCHEMAS["technical_spec"]]
        assert "propósito" in ts_names
        assert "alcance" in ts_names
        assert "componentes/conceptos" in ts_names
        assert "interfaces" in ts_names
        assert "restricciones" in ts_names
        assert "decisiones" in ts_names

    def test_policy_process_schema_has_expected_elements(self):
        """Policy/Process schema contains: propósito, alcance, actores/roles, reglas, procesos, excepciones."""
        pp_names = [
            entry["name"] for entry in DOCUMENT_TYPE_SCHEMAS["policy_process"]
        ]
        assert "propósito" in pp_names
        assert "alcance" in pp_names
        assert "actores/roles" in pp_names
        assert "reglas" in pp_names
        assert "procesos" in pp_names
        assert "excepciones" in pp_names


# --- Schema Structure Tests (Req 10.4) ---


class TestSchemaStructure:
    @pytest.mark.parametrize("doc_type", ["prd", "technical_spec", "policy_process"])
    def test_each_entry_has_required_fields(self, doc_type: str):
        """Every schema entry has name, description, and importance fields."""
        schema = DOCUMENT_TYPE_SCHEMAS[doc_type]
        for entry in schema:
            assert "name" in entry, f"Missing 'name' in {doc_type} entry: {entry}"
            assert "description" in entry, f"Missing 'description' in {doc_type} entry: {entry}"
            assert "importance" in entry, f"Missing 'importance' in {doc_type} entry: {entry}"

    @pytest.mark.parametrize("doc_type", ["prd", "technical_spec", "policy_process"])
    def test_importance_values_are_valid(self, doc_type: str):
        """Importance is one of: high, medium, low."""
        valid_levels = {"high", "medium", "low"}
        schema = DOCUMENT_TYPE_SCHEMAS[doc_type]
        for entry in schema:
            assert entry["importance"] in valid_levels, (
                f"Invalid importance '{entry['importance']}' in {doc_type} "
                f"entry '{entry['name']}'"
            )

    @pytest.mark.parametrize("doc_type", ["prd", "technical_spec", "policy_process"])
    def test_names_are_non_empty_strings(self, doc_type: str):
        """All name values are non-empty strings."""
        schema = DOCUMENT_TYPE_SCHEMAS[doc_type]
        for entry in schema:
            assert isinstance(entry["name"], str)
            assert len(entry["name"]) > 0

    @pytest.mark.parametrize("doc_type", ["prd", "technical_spec", "policy_process"])
    def test_descriptions_are_non_empty_strings(self, doc_type: str):
        """All description values are non-empty strings."""
        schema = DOCUMENT_TYPE_SCHEMAS[doc_type]
        for entry in schema:
            assert isinstance(entry["description"], str)
            assert len(entry["description"]) > 0

    @pytest.mark.parametrize("doc_type", ["prd", "technical_spec", "policy_process"])
    def test_schema_has_at_least_one_high_importance(self, doc_type: str):
        """Each schema has at least one high-importance element."""
        schema = DOCUMENT_TYPE_SCHEMAS[doc_type]
        high_elements = [e for e in schema if e["importance"] == "high"]
        assert len(high_elements) >= 1


# --- get_schema Helper Tests (Req 3.3, 3.4) ---


class TestGetSchema:
    def test_generic_returns_none(self):
        """get_schema('generic') returns None (Req 3.3)."""
        assert get_schema("generic") is None

    def test_unknown_type_returns_none(self):
        """get_schema with an unknown type returns None."""
        assert get_schema("unknown_type") is None

    def test_empty_string_returns_none(self):
        """get_schema('') returns None."""
        assert get_schema("") is None

    def test_prd_returns_schema(self):
        """get_schema('prd') returns the PRD schema list."""
        result = get_schema("prd")
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 5

    def test_technical_spec_returns_schema(self):
        """get_schema('technical_spec') returns the Technical Spec schema list."""
        result = get_schema("technical_spec")
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 6

    def test_policy_process_returns_schema(self):
        """get_schema('policy_process') returns the Policy/Process schema list."""
        result = get_schema("policy_process")
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 6

    def test_returned_schema_matches_dict(self):
        """get_schema returns the same object as DOCUMENT_TYPE_SCHEMAS[type]."""
        for doc_type in ["prd", "technical_spec", "policy_process"]:
            assert get_schema(doc_type) is DOCUMENT_TYPE_SCHEMAS[doc_type]
