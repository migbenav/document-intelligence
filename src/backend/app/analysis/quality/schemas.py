"""Document type schemas for completeness evaluation.

Defines the expected elements per document type (from ADR-006).
Used by the CompletenessEvaluator to determine what elements
a document should contain based on its confirmed type.

Requirements validated: 3.4, 10.4
"""

DOCUMENT_TYPE_SCHEMAS: dict[str, list[dict[str, str]]] = {
    "prd": [
        {
            "name": "propósito",
            "description": "Document purpose and product goal",
            "importance": "high",
        },
        {
            "name": "usuarios/actores",
            "description": "Target users and actors",
            "importance": "high",
        },
        {
            "name": "requisitos funcionales",
            "description": "Functional requirements",
            "importance": "high",
        },
        {
            "name": "restricciones",
            "description": "Constraints and limitations",
            "importance": "medium",
        },
        {
            "name": "criterios de éxito",
            "description": "Success criteria and metrics",
            "importance": "medium",
        },
    ],
    "technical_spec": [
        {
            "name": "propósito",
            "description": "Specification purpose and scope",
            "importance": "high",
        },
        {
            "name": "alcance",
            "description": "System scope and boundaries",
            "importance": "high",
        },
        {
            "name": "componentes/conceptos",
            "description": "System components and key concepts",
            "importance": "high",
        },
        {
            "name": "interfaces",
            "description": "API interfaces and contracts",
            "importance": "medium",
        },
        {
            "name": "restricciones",
            "description": "Technical constraints",
            "importance": "medium",
        },
        {
            "name": "decisiones",
            "description": "Design decisions and rationale",
            "importance": "low",
        },
    ],
    "policy_process": [
        {
            "name": "propósito",
            "description": "Policy/process purpose",
            "importance": "high",
        },
        {
            "name": "alcance",
            "description": "Scope of applicability",
            "importance": "high",
        },
        {
            "name": "actores/roles",
            "description": "Involved actors and roles",
            "importance": "high",
        },
        {
            "name": "reglas",
            "description": "Business rules and policies",
            "importance": "high",
        },
        {
            "name": "procesos",
            "description": "Process steps and workflows",
            "importance": "medium",
        },
        {
            "name": "excepciones",
            "description": "Exceptions and edge cases",
            "importance": "low",
        },
    ],
}


def get_schema(document_type: str) -> list[dict[str, str]] | None:
    """Return the schema for a document type, or None for generic/unknown types.

    Args:
        document_type: The confirmed document type (e.g., "prd", "technical_spec",
            "policy_process", "generic").

    Returns:
        A list of expected element definitions for the document type,
        or None if the type is "generic" or not recognized.
    """
    if document_type == "generic":
        return None
    return DOCUMENT_TYPE_SCHEMAS.get(document_type)
