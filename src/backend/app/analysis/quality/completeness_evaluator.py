"""Completeness evaluator for document quality analysis.

Evaluates document completeness against the document type schema by:
1. Deterministically matching KM elements against schema expected elements.
2. Using LLM to assess partial coverage for present elements.

Requirements covered: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 8.3, 10.4, 10.5
"""

import json
import logging
import uuid

from app.analysis.llm_client import LLMClient
from app.analysis.prompts import completeness_evaluation_v1
from app.analysis.quality.schemas import get_schema
from app.models.knowledge_model import KnowledgeModel
from app.models.quality_analysis import MissingElement

logger = logging.getLogger(__name__)


class CompletenessEvaluationError(Exception):
    """Raised when completeness evaluation cannot proceed."""

    pass


class CompletenessEvaluator:
    """Evaluates document completeness against type schemas.

    Constructor receives LLMClient for partial coverage assessment.
    The evaluate() method performs deterministic matching (present vs missing)
    and then uses LLM to assess partial coverage for present elements.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialize with LLM client for partial coverage assessment.

        Args:
            llm_client: The LLM client used for assessing partial coverage.
        """
        self._llm_client = llm_client

    async def evaluate(
        self,
        knowledge_model: KnowledgeModel,
        document_type: str,
    ) -> list[MissingElement]:
        """Compare KM elements against the document type schema.

        Schema matching (present vs missing) is deterministic.
        The "partial" classification uses LLM to assess content depth
        via the completeness_evaluation_v1.py prompt.

        Returns empty list for "generic" type (Req 3.3).
        Raises error for empty Knowledge Models (Req 3.6).

        Args:
            knowledge_model: The completed Knowledge Model to evaluate.
            document_type: The confirmed document type.

        Returns:
            List of MissingElement findings for missing and partial elements.

        Raises:
            CompletenessEvaluationError: When KM is empty or schema is not found.
        """
        # Req 3.3: Generic type returns empty list immediately
        if document_type == "generic":
            return []

        # Req 3.6: Empty KM raises error
        if not knowledge_model.elements:
            raise CompletenessEvaluationError(
                "Completeness cannot be assessed: Knowledge Model contains zero elements."
            )

        # Req 10.4: Load schema; if None, fail
        schema = get_schema(document_type)
        if schema is None:
            raise CompletenessEvaluationError(
                f"Document type schema not found for type '{document_type}'. "
                "Completeness evaluation cannot proceed without a valid schema."
            )

        # Step 1 (deterministic): Match KM elements against schema
        present_elements, missing_elements = self._match_elements(
            knowledge_model, schema
        )

        # Build findings for missing elements
        findings: list[MissingElement] = []
        for schema_entry in missing_elements:
            findings.append(
                MissingElement(
                    id=f"miss-{uuid.uuid4().hex[:8]}",
                    classification="missing",
                    expected_element=schema_entry["name"],
                    description=f"Expected element '{schema_entry['name']}' ({schema_entry['description']}) is not present in the document.",
                    severity=schema_entry["importance"],
                    schema_reference=document_type,
                )
            )

        # Step 2 (LLM): Assess partial coverage for present elements
        if present_elements:
            partial_findings = await self._assess_partial_coverage(
                knowledge_model, present_elements, schema, document_type
            )
            findings.extend(partial_findings)

        return findings

    def _match_elements(
        self,
        knowledge_model: KnowledgeModel,
        schema: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        """Deterministically match KM elements against schema expected elements.

        Uses case-insensitive substring matching to compare KM element
        type/name against schema expected element names.

        Args:
            knowledge_model: The Knowledge Model to check.
            schema: The document type schema entries.

        Returns:
            Tuple of (present_elements, missing_elements) from the schema.
        """
        present: list[dict[str, str]] = []
        missing: list[dict[str, str]] = []

        for schema_entry in schema:
            expected_name = schema_entry["name"].lower()
            found = False

            for element in knowledge_model.elements:
                element_name = element.name.lower()
                element_type = element.type.lower()

                # Match by: schema name is substring of element name/type,
                # or element name/type is substring of schema name
                if (
                    expected_name in element_name
                    or expected_name in element_type
                    or element_name in expected_name
                    or element_type in expected_name
                ):
                    found = True
                    break

            if found:
                present.append(schema_entry)
            else:
                missing.append(schema_entry)

        return present, missing

    async def _assess_partial_coverage(
        self,
        knowledge_model: KnowledgeModel,
        present_elements: list[dict[str, str]],
        schema: list[dict[str, str]],
        document_type: str,
    ) -> list[MissingElement]:
        """Use LLM to assess whether present elements have full or partial coverage.

        Args:
            knowledge_model: The Knowledge Model containing the elements.
            present_elements: Schema entries that have matching KM elements.
            schema: The full schema for context.
            document_type: The document type for schema_reference.

        Returns:
            List of MissingElement findings for partially covered elements.
        """
        # Build matched elements JSON for the prompt
        matched_data = []
        for schema_entry in present_elements:
            matching_km_elements = self._find_matching_km_elements(
                knowledge_model, schema_entry
            )
            matched_data.append(
                {
                    "expected_element_name": schema_entry["name"],
                    "schema_description": schema_entry["description"],
                    "km_elements": [
                        {"name": e.name, "type": e.type, "content": e.content}
                        for e in matching_km_elements
                    ],
                }
            )

        elements_json = json.dumps(matched_data, ensure_ascii=False, indent=2)
        schema_json = json.dumps(schema, ensure_ascii=False, indent=2)

        # Build and call the LLM prompt
        prompt = completeness_evaluation_v1.build(elements_json, schema_json)
        response = await self._llm_client.call(prompt, model_tier="primary", temperature=0.1)

        # Parse the LLM response
        partial_findings = self._parse_llm_response(response.content, document_type)
        return partial_findings

    def _find_matching_km_elements(
        self,
        knowledge_model: KnowledgeModel,
        schema_entry: dict[str, str],
    ) -> list:
        """Find all KM elements matching a schema entry.

        Args:
            knowledge_model: The Knowledge Model to search.
            schema_entry: The schema entry to match against.

        Returns:
            List of matching KnowledgeElement objects.
        """
        expected_name = schema_entry["name"].lower()
        matches = []

        for element in knowledge_model.elements:
            element_name = element.name.lower()
            element_type = element.type.lower()

            if (
                expected_name in element_name
                or expected_name in element_type
                or element_name in expected_name
                or element_type in expected_name
            ):
                matches.append(element)

        return matches

    def _parse_llm_response(
        self,
        content: str,
        document_type: str,
    ) -> list[MissingElement]:
        """Parse LLM response into MissingElement findings for partial elements.

        Args:
            content: Raw LLM response content (JSON string).
            document_type: The document type for schema_reference.

        Returns:
            List of MissingElement findings for elements classified as partial.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON for completeness evaluation")
            return []

        findings: list[MissingElement] = []
        assessments = data.get("assessments", [])

        for assessment in assessments:
            classification = assessment.get("classification", "").lower()
            if classification == "partial":
                severity = assessment.get("severity", "medium")
                if severity not in ("high", "medium", "low"):
                    severity = "medium"

                findings.append(
                    MissingElement(
                        id=f"miss-{uuid.uuid4().hex[:8]}",
                        classification="partial",
                        expected_element=assessment.get("expected_element_name", "unknown"),
                        description=assessment.get("description", "Element partially covers the expected content."),
                        severity=severity,
                        schema_reference=document_type,
                    )
                )

        return findings
