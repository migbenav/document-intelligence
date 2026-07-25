"""Versioned prompt template for ambiguity detection in document quality analysis.

Instructs the LLM to identify ambiguous, vague, or unclear statements in a document
using Knowledge Model elements and IR text as context. Detects four ambiguity categories:
undefined terms, vague quantifiers, unclear pronoun antecedents, and unspecified conditions.

Requirements covered: 2.1, 2.2, 2.3, 9.2, 10.1, 10.7, 10.8
"""

VERSION = "ambiguity-v1"

_AMBIGUITY_CATEGORIES = (
    "undefined_term",
    "vague_quantifier",
    "unclear_pronoun_antecedent",
    "unspecified_condition",
)

_SYSTEM_INSTRUCTIONS = """\
You are a document quality analysis engine specializing in ambiguity detection. \
Your task is to identify statements in the provided document that are ambiguous, \
vague, or can be interpreted in multiple valid ways.

## Ambiguity Categories

Detect ambiguities in the following categories:

1. **Undefined Terms**: Terms used without prior definition or context that leave \
their meaning open to interpretation. Example: "the system shall use appropriate \
measures" — "appropriate" is undefined.

2. **Vague Quantifiers**: Quantifiers or modifiers without specific measurable \
values. Example: "the response should be fast", "handle many requests", \
"adequate performance" — "fast", "many", and "adequate" lack precision.

3. **Unclear Pronoun Antecedents**: Pronouns (it, they, this, that, these, those) \
whose referent is ambiguous because multiple valid antecedents exist in context. \
Example: "The server sends data to the client. It then processes the result." — \
"It" could refer to either the server or the client.

4. **Unspecified Conditions**: Conditional statements where the triggering \
conditions are incomplete, vague, or unspecified. Example: "Under certain \
circumstances, the system will retry" — the circumstances are not defined.

## Severity Criteria

Assign severity based on the impact of the ambiguity:

- **high**: Blocks comprehension of a core element — the reader cannot understand \
the fundamental meaning or intent of the statement without clarification.
- **medium**: Creates uncertainty in a secondary element — the reader can understand \
the general intent but specific details or boundaries remain unclear.
- **low**: Stylistic imprecision with minimal misinterpretation risk — the meaning \
is largely clear from context but the wording could be more precise.

## Interpretation Requirement

For EVERY ambiguity finding, you MUST provide at least 2 plausible interpretations \
of the ambiguous statement. Each interpretation must be a distinct, reasonable way \
the statement could be understood. Include these interpretations in the finding \
description to demonstrate why the statement is genuinely ambiguous.

## Output Schema

Respond with valid JSON matching this exact schema:

"""

_JSON_SCHEMA = """\
{
  "ambiguities": [
    {
      "id": "<unique-id, e.g. amb-001>",
      "category": "<one of: undefined_term, vague_quantifier, unclear_pronoun_antecedent, unspecified_condition>",
      "description": "<description of the ambiguity including at least 2 plausible interpretations, max 500 characters>",
      "severity": "<one of: high, medium, low>",
      "affected_element_ids": ["<KM element ID involved in this ambiguity>"],
      "source_ref": {
        "chunk_id": "<IR chunk ID where the ambiguous text was found>",
        "page": "<page number or null>",
        "section": "<section heading or null>",
        "evidence": "<VERBATIM text span from the document containing the ambiguity, max 500 characters>"
      }
    }
  ]
}"""

_SYSTEM_INSTRUCTIONS_FOOTER = """\

## Rules

1. Use ONLY the ambiguity categories defined above. No other categories are allowed.
2. Every finding MUST include at least 2 plausible interpretations in the description.
3. Every finding MUST include a source_ref with verbatim evidence from the document text.
4. The evidence field must be a direct quote — do not paraphrase or summarize.
5. Severity must follow the criteria defined above strictly.
6. If no ambiguities are found, return: {"ambiguities": []}
7. Do not fabricate findings. Only report genuine ambiguities present in the text.
8. Do not include any information about users, sessions, accounts, or metadata \
not present in the document text itself.
9. Respond ONLY with the JSON object. No explanatory text before or after.
10. Finding IDs must be unique within the output (use format: amb-001, amb-002, etc.).
11. The description must not exceed 500 characters.
12. The evidence text span must not exceed 500 characters.\
"""


def build(elements_json: str, ir_text: str) -> str:
    """Construct the ambiguity detection prompt from KM elements and IR text.

    Args:
        elements_json: JSON string of Knowledge Model elements providing
            semantic context for ambiguity detection. Contains only element
            types, names, content, and relationships — no user metadata.
        ir_text: The IR text content (document chunks) to analyze for
            ambiguities. Contains only document text and structural markers.
            Must NOT contain user metadata or session info (Req 9.2).

    Returns:
        The complete prompt string ready to send to the LLM.
    """
    instructions = _SYSTEM_INSTRUCTIONS + _JSON_SCHEMA + _SYSTEM_INSTRUCTIONS_FOOTER

    return f"""{instructions}

--- KNOWLEDGE MODEL ELEMENTS ---
{elements_json}
--- END KNOWLEDGE MODEL ELEMENTS ---

--- DOCUMENT TEXT ---
{ir_text}
--- END DOCUMENT TEXT ---"""
