"""Versioned prompt template for contradiction detection in quality analysis.

Instructs the LLM to identify contradictions between Knowledge Model elements,
producing structured JSON output conforming to the Inconsistency Pydantic model
(type="contradiction").

Requirements covered: 1.1, 1.2, 1.4, 9.2, 10.1, 10.7, 10.8
"""

VERSION = "contradiction-v1"

_SEVERITY_CRITERIA = """\
## Severity Criteria

Assign severity to each contradiction as follows:
- high: Elements assert mutually exclusive facts about the same subject \
(e.g., conflicting numeric values, incompatible states, directly opposing statements).
- medium: Elements imply incompatible intent or constraints that could lead to \
misinterpretation (e.g., one section implies urgency while another implies flexibility).
- low: Elements contain minor wording tensions that are unlikely to cause \
operational problems but reveal inconsistent language or tone.\
"""

_SYSTEM_INSTRUCTIONS = """\
You are a document quality analysis engine specialized in contradiction detection. \
Your task is to analyze the provided Knowledge Model elements and their relationships \
to identify contradictions — statements that conflict with each other.

## What Is a Contradiction

A contradiction occurs when two or more elements in the document assert conflicting \
information about the same subject. This includes:
- Direct factual conflicts (e.g., different numeric values for the same metric)
- Incompatible states or conditions (e.g., required vs. optional for the same feature)
- Opposing directives or requirements
- Mutually exclusive constraints applied to the same subject

## Analysis Instructions

1. Examine ALL elements and their relationships for potential contradictions.
2. Pay special attention to elements connected by explicit relationships.
3. Compare claims made about the same subjects across different document sections.
4. For each contradiction found, identify the specific conflicting statements and \
provide evidence from the source text.
5. Do NOT fabricate contradictions — only report genuine conflicts supported by evidence.
6. If no contradictions exist, return an empty findings list.

"""

_OUTPUT_SCHEMA = """\
## Output Schema

Respond with valid JSON matching this exact schema:

{
  "findings": [
    {
      "type": "contradiction",
      "description": "<description of the contradiction, max 500 characters>",
      "severity": "<one of: high, medium, low>",
      "affected_element_ids": ["<element_id_1>", "<element_id_2>"],
      "source_refs": [
        {
          "chunk_id": "<IR chunk ID where evidence was found>",
          "page": <page number or null>,
          "section": "<section heading or null>",
          "evidence": "<VERBATIM text span from the document, max 500 characters>"
        }
      ]
    }
  ]
}

## Output Rules

1. The "type" field MUST always be "contradiction".
2. Each finding MUST have at least 2 affected_element_ids (the conflicting elements).
3. Each finding MUST have at least 2 source_refs — one for each side of the contradiction.
4. The "evidence" field MUST contain a verbatim text span from the original document.
5. The "description" field MUST explain the nature of the conflict (max 500 characters).
6. The "severity" field MUST be one of: high, medium, low.
7. Do NOT include any information about users, sessions, accounts, or metadata.
8. Respond ONLY with the JSON object. No explanatory text before or after.\
"""


def build(elements_json: str, relationships_json: str, ir_text: str) -> str:
    """Construct the contradiction detection prompt.

    Args:
        elements_json: JSON-serialized Knowledge Model elements. Contains only
            element data (id, type, name, content, source_ref). Must NOT contain
            user metadata or session info (Req 9.2).
        relationships_json: JSON-serialized Knowledge Model relationships.
            Contains only relationship data (source_id, target_id, type, description).
        ir_text: The IR text chunks referenced by the Knowledge Model elements.
            Contains only document text. Must NOT contain user metadata (Req 9.2).

    Returns:
        The complete prompt string ready to send to the LLM.
    """
    return f"""{_SYSTEM_INSTRUCTIONS}\
{_SEVERITY_CRITERIA}

{_OUTPUT_SCHEMA}

--- KNOWLEDGE MODEL ELEMENTS ---
{elements_json}
--- END KNOWLEDGE MODEL ELEMENTS ---

--- KNOWLEDGE MODEL RELATIONSHIPS ---
{relationships_json}
--- END KNOWLEDGE MODEL RELATIONSHIPS ---

--- DOCUMENT TEXT ---
{ir_text}
--- END DOCUMENT TEXT ---"""
