"""Versioned prompt template for query answering.

Instructs the LLM to answer a natural language question using provided Knowledge Model
context elements and relationships, producing a structured JSON response with grounded
evidence references.

Requirements covered: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 2.6, 7.2
"""

VERSION = "query-answering-v1"

_SYSTEM_INSTRUCTIONS = """\
You are a document knowledge assistant. Your task is to answer the user's question \
using ONLY the provided Knowledge Model context. Every claim in your answer must be \
grounded in at least one verbatim evidence span from the context.

## Instructions

1. Answer the question directly and concisely based ONLY on the provided context elements.
2. Do NOT use any information from your parametric knowledge — only the context below.
3. Ground EVERY claim in your answer to at least one evidence span from the context.
4. If a claim requires reasoning beyond what is directly stated in the context, \
do NOT include it in your answer.
5. If the context does not contain sufficient information to answer the question, \
return the "cannot answer" response (see output schema below).
6. Elements marked with [UNVERIFIED] have not been verified against the original document. \
You may still use them, but note reduced confidence in claims derived solely from \
unverified elements.
7. Include between 1 and 10 evidence references that support your answer. Each evidence \
reference must be a verbatim text span copied from the context elements' evidence fields.
8. Do NOT fabricate evidence — only reference text that appears verbatim in the provided context.

"""

_OUTPUT_SCHEMA = """\
## Output Schema

Respond with valid JSON matching this exact schema:

{
  "answer": "<direct answer to the question, max 5000 characters>",
  "answerable": true,
  "source_refs": [
    {
      "chunk_id": "<chunk_id from the context element's evidence>",
      "page": <page number or null>,
      "section": "<section heading or null>",
      "evidence": "<VERBATIM text span from context, max 500 characters>"
    }
  ]
}

## When the question CANNOT be answered from context:

{
  "answer": "<explanation of why the question cannot be answered from available knowledge>",
  "answerable": false,
  "source_refs": []
}

## Output Rules

1. The "answer" field MUST be a direct response to the question (max 5000 characters).
2. When "answerable" is true, "source_refs" MUST contain between 1 and 10 references.
3. When "answerable" is false, "source_refs" MUST be an empty list.
4. The "evidence" field in each source_ref MUST be a verbatim text span from the \
context elements (max 500 characters). Do NOT paraphrase or modify the evidence text.
5. Every distinct factual claim in the answer MUST have at least one corresponding \
source_ref with evidence supporting that claim.
6. Do NOT include any information about users, sessions, accounts, document IDs, or metadata.
7. Respond ONLY with the JSON object. No explanatory text before or after.
8. If you cannot determine the answer from the provided context, set "answerable" to false \
and explain what information is missing or unavailable.\
"""


def build(context_elements: list, relations: list, question: str) -> str:
    """Construct the query answering prompt from context and question.

    Args:
        context_elements: List of context element dicts, each with keys:
            'type', 'name', 'content', 'evidence', and optionally 'verified'
            (bool indicating verification status). Elements with verified=False
            are annotated with [UNVERIFIED] in the prompt.
            Must NOT contain user metadata, session info, account data,
            or document_id (Req 2.6, 7.2).
        relations: List of relation dicts, each with keys:
            'source_id', 'target_id', 'type'. Only relationship structure
            is included — no user or session data.
        question: The user's natural language question as a plain string.
            No user identity or session context is attached.

    Returns:
        The complete prompt string ready to send to the LLM.
    """
    elements_section = _format_context_elements(context_elements)
    relations_section = _format_relations(relations)

    return f"""{_SYSTEM_INSTRUCTIONS}\
{_OUTPUT_SCHEMA}

--- KNOWLEDGE MODEL CONTEXT ---
{elements_section}
--- END KNOWLEDGE MODEL CONTEXT ---

--- RELATIONSHIPS ---
{relations_section}
--- END RELATIONSHIPS ---

--- QUESTION ---
{question}
--- END QUESTION ---"""


def _format_context_elements(context_elements: list) -> str:
    """Format context elements into a readable section for the prompt.

    Args:
        context_elements: List of element dicts with keys:
            type, name, content, evidence, and optionally verified.

    Returns:
        Formatted string representing all context elements.
    """
    if not context_elements:
        return "No context elements available."

    lines: list[str] = []
    for elem in context_elements:
        verified = elem.get("verified", True)
        unverified_marker = " [UNVERIFIED]" if not verified else ""

        elem_type = elem.get("type", "unknown")
        name = elem.get("name", "")
        content = elem.get("content", "")
        evidence = elem.get("evidence", "")

        lines.append(
            f"- Type: {elem_type}{unverified_marker}\n"
            f"  Name: {name}\n"
            f"  Content: {content}\n"
            f"  Evidence: {evidence}"
        )

    return "\n\n".join(lines)


def _format_relations(relations: list) -> str:
    """Format relations into a readable section for the prompt.

    Args:
        relations: List of relation dicts with keys:
            source_id, target_id, type.

    Returns:
        Formatted string representing all relations.
    """
    if not relations:
        return "No relationships available."

    lines: list[str] = []
    for rel in relations:
        source_id = rel.get("source_id", "")
        target_id = rel.get("target_id", "")
        rel_type = rel.get("type", "")
        lines.append(f"- {source_id} --[{rel_type}]--> {target_id}")

    return "\n".join(lines)
