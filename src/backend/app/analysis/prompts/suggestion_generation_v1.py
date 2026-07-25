"""Versioned prompt template for quality analysis suggestion generation.

Instructs the LLM to generate actionable improvement suggestions from quality
findings (contradictions, ambiguities, missing elements) and the Knowledge Model context.

Each suggestion must be a concrete recommended action, not a restatement of a problem.

Requirements covered: 4.1, 4.2, 4.3, 9.2, 10.1, 10.7, 10.8
"""

VERSION = "suggestion-v1"

_CATEGORIES = ("structure", "clarity", "completeness", "consistency")

_PRIORITY_MAPPING = {
    "high": "Addresses a high-severity finding",
    "medium": "Addresses a medium-severity finding or structural gap",
    "low": "Addresses a low-severity finding or stylistic improvement",
}

_SYSTEM_INSTRUCTIONS = """\
You are a document quality improvement engine. Your task is to generate actionable \
improvement suggestions based on the quality findings and document context provided below.

## Core Principle: Actionability

Every suggestion MUST describe a specific, concrete action the author should take to \
improve the document. Suggestions MUST NOT be restatements of problems. Each suggestion \
describes WHAT TO DO, not what is wrong.

GOOD example: "Add a section defining the maximum response time for each endpoint with \
specific SLA values."
BAD example: "Performance requirements are vague."

## Suggestion Categories

Assign each suggestion to exactly ONE of these categories:
- structure: Improvements to document organization, section ordering, or information hierarchy.
- clarity: Improvements to reduce ambiguity, define terms, or clarify statements.
- completeness: Additions of missing content, sections, or details expected by the document type.
- consistency: Changes to resolve contradictions or align conflicting statements.

## Priority Mapping

Assign priority based on the severity of the related finding:
- high: Addresses a high-severity finding (mutually exclusive facts, missing critical sections, \
comprehension-blocking ambiguity).
- medium: Addresses a medium-severity finding or a structural gap.
- low: Addresses a low-severity finding or a stylistic improvement.

## Constraints

1. Maximum 300 characters per suggestion description. Be concise but specific.
2. Each suggestion MUST include at least one source_ref pointing to the document context \
where the improvement applies.
3. Maximum 20 suggestions per analysis run. Prioritize the most impactful improvements.
4. Generate at least one suggestion for every high-severity finding provided.
5. Do not fabricate suggestions when no findings exist and no improvement opportunities \
are evident.

## Output Schema

Respond with valid JSON matching this exact schema:

"""

_JSON_SCHEMA = """\
{
  "suggestions": [
    {
      "id": "<unique-id, e.g. sug-001>",
      "description": "<concrete action to improve the document, max 300 characters>",
      "category": "<one of: structure, clarity, completeness, consistency>",
      "priority": "<one of: high, medium, low>",
      "related_finding_ids": ["<optional list of finding IDs this suggestion addresses>"],
      "source_refs": [
        {
          "chunk_id": "<IR chunk ID where improvement applies>",
          "page": "<page number or null>",
          "section": "<section heading or null>",
          "evidence": "<verbatim text span from the document providing context, max 500 chars>"
        }
      ]
    }
  ]
}"""

_SYSTEM_INSTRUCTIONS_FOOTER = """\

## Rules

1. Use ONLY the categories listed above. No other categories are allowed.
2. Use ONLY the priority levels listed above (high, medium, low).
3. Every suggestion MUST have a non-empty description of maximum 300 characters.
4. Every suggestion MUST include at least one source_ref with a non-empty evidence field.
5. Suggestion IDs must be unique within the output (use format: sug-001, sug-002, etc.).
6. Do not include any information about users, sessions, accounts, or metadata not present \
in the document content.
7. Respond ONLY with the JSON object. No explanatory text before or after.
8. Focus on actionability — every description must start with a verb or action phrase.
9. Do not generate more than 20 suggestions total.
10. Generate at least one suggestion for each high-severity finding in the input.\
"""


def build(findings_json: str, elements_json: str, ir_text: str) -> str:
    """Construct the suggestion generation prompt from findings and KM context.

    Args:
        findings_json: JSON-serialized list of quality findings (contradictions,
            ambiguities, missing elements) that suggestions should address.
            Contains only finding data — no user metadata (Req 9.2).
        elements_json: JSON-serialized Knowledge Model elements providing
            document context for suggestion generation.
            Contains only KM element data — no user metadata (Req 9.2).
        ir_text: The IR text chunks referenced by KM elements, providing
            the original document text for source_ref generation.
            Must NOT contain user metadata or session info (Req 9.2).

    Returns:
        The complete prompt string ready to send to the LLM.
    """
    instructions = _SYSTEM_INSTRUCTIONS + _JSON_SCHEMA + _SYSTEM_INSTRUCTIONS_FOOTER

    return f"""{instructions}

--- QUALITY FINDINGS ---
{findings_json}
--- END QUALITY FINDINGS ---

--- KNOWLEDGE MODEL ELEMENTS ---
{elements_json}
--- END KNOWLEDGE MODEL ELEMENTS ---

--- DOCUMENT TEXT ---
{ir_text}
--- END DOCUMENT TEXT ---"""
