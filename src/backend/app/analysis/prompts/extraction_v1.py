"""Versioned prompt template for Knowledge Model extraction.

Instructs the LLM to extract structured knowledge elements and relationships
from a document's IR text using the fixed taxonomy and relationship vocabulary.

Requirements covered: 2.1, 2.2, 2.3, 2.4, 2.5, 5.1, 6.1, 10.1
"""

VERSION = "extraction-v1"

_TAXONOMY = ("proposito", "concepto", "actor", "regla", "proceso", "restriccion")

_RELATIONSHIP_VOCABULARY = ("constrains", "participates_in", "depends_on", "contradicts")

_SYSTEM_INSTRUCTIONS_HEADER = """\
You are a knowledge extraction engine. Your task is to analyze the provided document \
and produce a structured Knowledge Model by extracting typed elements and their relationships.

## Element Taxonomy

Extract elements using ONLY these types:
- proposito: The purpose, goal, or objective described in the document.
- concepto: A key concept, term, or definition.
- actor: A person, role, system, or entity that participates in processes or is referenced.
- regla: A rule, requirement, constraint, or business logic statement.
- proceso: A process, workflow, procedure, or sequence of steps.
- restriccion: A limitation, boundary condition, non-functional requirement, or constraint.

Every document MUST have at least one "proposito" element representing the document's purpose.

## Relationship Vocabulary

Identify relationships between elements using ONLY these types:
- constrains: The source element imposes a constraint on the target element.
- participates_in: The source element participates in or is involved in the target element.
- depends_on: The source element depends on or requires the target element.
- contradicts: The source element contradicts or conflicts with the target element. \
This relationship is always bidirectional.

Only include relationships you are confident about. Do not force relationships where none exist.

## Evidence Requirement

For EVERY element you extract, you MUST include a verbatim evidence field containing \
an exact text span copied directly from the source document that supports the element's \
existence. The evidence must be a direct quote — do not paraphrase or summarize. \
Each element's source_ref.evidence field must contain this verbatim text span.

## Output Schema

Respond with valid JSON matching this exact schema:

"""

_JSON_SCHEMA = """\
{
  "elements": [
    {
      "id": "<unique-id, e.g. elem-001>",
      "type": "<one of: proposito, concepto, actor, regla, proceso, restriccion>",
      "name": "<short label for this element>",
      "content": "<description of the element>",
      "source_ref": {
        "chunk_id": "<IR chunk ID where evidence was found>",
        "page": "<page number or null>",
        "section": "<section heading or null>",
        "evidence": "<VERBATIM text span from the document proving this element>"
      },
      "relations": [
        {
          "target_id": "<id of the related element>",
          "type": "<one of: constrains, participates_in, depends_on, contradicts>",
          "description": "<optional brief description of the relationship>"
        }
      ]
    }
  ]
}"""

_SYSTEM_INSTRUCTIONS_FOOTER = """\

## Rules

1. Use ONLY the element types from the taxonomy above. No other types are allowed.
2. Use ONLY the relationship types from the vocabulary above. No other types are allowed.
3. Every element MUST have a non-empty evidence field with a verbatim quote from the document.
4. Element IDs must be unique within the output (use format: elem-001, elem-002, etc.).
5. Relationship target_id must reference an element ID that exists in your output.
6. Do not include any information about users, sessions, accounts, or metadata not present \
in the document text itself.
7. Respond ONLY with the JSON object. No explanatory text before or after.
8. Extract all significant knowledge elements — be thorough but precise.
9. For the "contradicts" relationship type, always create the relationship in both directions.\
"""


def build(ir_text: str, document_type: str, structural_contexts: list[dict]) -> str:
    """Construct the extraction prompt from IR text and document metadata.

    Args:
        ir_text: The full IR text content (all chunks concatenated).
            Contains only document text and structural markers.
            Must NOT contain user metadata or session info (Req 2.4).
        document_type: The confirmed document type (prd, technical_spec,
            policy_process, or generic).
        structural_contexts: List of structural context dicts, each with keys
            like 'chunk_id', 'section', 'page' to provide location context
            for the LLM.

    Returns:
        The complete prompt string ready to send to the LLM.
    """
    # Format structural context section
    context_section = _format_structural_contexts(structural_contexts)

    # Build the document type context section
    doc_type_section = _build_document_type_section(document_type)

    # Assemble the full prompt from parts (avoids .format() issues with JSON braces)
    instructions = (
        _SYSTEM_INSTRUCTIONS_HEADER
        + _JSON_SCHEMA
        + _SYSTEM_INSTRUCTIONS_FOOTER
        + "\n\n"
        + doc_type_section
    )

    return f"""{instructions}

--- STRUCTURAL CONTEXT ---
{context_section}
--- END STRUCTURAL CONTEXT ---

--- DOCUMENT TEXT ---
{ir_text}
--- END DOCUMENT TEXT ---"""


def _build_document_type_section(document_type: str) -> str:
    """Build the document type context section for the prompt.

    Args:
        document_type: The confirmed document type.

    Returns:
        Formatted document type context instructions.
    """
    return (
        f"## Document Type Context\n\n"
        f"The document has been classified as: {document_type}\n\n"
        f"Use this classification to inform your extraction priorities:\n"
        f"- prd: Focus on user stories, acceptance criteria, features (regla), actors, and processes.\n"
        f"- technical_spec: Focus on system components (concepto), APIs (proceso), constraints (restriccion).\n"
        f"- policy_process: Focus on rules (regla), processes (proceso), actors, and restrictions.\n"
        f"- generic: Apply balanced extraction across all element types."
    )


def _format_structural_contexts(structural_contexts: list[dict]) -> str:
    """Format structural contexts into a readable section for the prompt.

    Args:
        structural_contexts: List of dicts with chunk location information.

    Returns:
        Formatted string describing the document structure.
    """
    if not structural_contexts:
        return "No structural context available."

    lines: list[str] = []
    for ctx in structural_contexts:
        parts: list[str] = []
        if chunk_id := ctx.get("chunk_id"):
            parts.append(f"chunk_id={chunk_id}")
        if section := ctx.get("section"):
            parts.append(f"section=\"{section}\"")
        if page := ctx.get("page"):
            parts.append(f"page={page}")
        if parts:
            lines.append(", ".join(parts))

    return "\n".join(lines) if lines else "No structural context available."
