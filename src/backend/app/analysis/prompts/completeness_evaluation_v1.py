"""Versioned prompt template for completeness evaluation (partial coverage assessment).

Instructs the LLM to assess whether elements that exist in the Knowledge Model
adequately cover their schema definition or only partially address it.

This prompt is used by the CompletenessEvaluator when an element has been
identified as present in the Knowledge Model — the LLM determines if the
coverage is full or partial based on the document type schema expectations.

Requirements covered: 3.1, 3.5, 9.2, 10.4, 10.7, 10.8
"""

VERSION = "completeness-v1"

_SYSTEM_INSTRUCTIONS = """\
You are a document completeness assessor. Your task is to evaluate whether \
elements present in a Knowledge Model adequately cover their expected schema \
definition or only partially address it.

## Task

You will receive:
1. A list of Knowledge Model elements that have been matched to expected schema elements.
2. The document type schema defining what each expected element should contain.

For each matched element, determine if the Knowledge Model content **fully covers** \
the schema definition or **only partially addresses** it.

## Classification Criteria

An element is classified as **partial** when it covers fewer than half of the \
sub-aspects implied by its schema definition. Specifically:

- **full**: The element's content substantively addresses the schema definition. \
It covers the majority of what the schema expects for that element type.
- **partial**: The element exists but covers fewer than half of the sub-aspects \
implied by its schema definition. Key aspects expected by the schema are missing \
or insufficiently addressed.

## Assessment Rules

1. Evaluate ONLY the elements provided — do not infer or fabricate additional elements.
2. Compare each element's actual content against the schema definition to determine coverage.
3. Consider the depth and breadth of coverage, not just the presence of keywords.
4. An element that mentions a topic superficially without substantive detail is partial.
5. An element that addresses most aspects of its schema definition is full.

## Output Schema

Respond with valid JSON matching this exact schema:

"""

_JSON_SCHEMA = """\
{
  "assessments": [
    {
      "expected_element_name": "<name of the expected element from the schema>",
      "classification": "<one of: full, partial>",
      "description": "<explanation of what additional content is expected if partial, or confirmation of adequate coverage if full>",
      "severity": "<one of: high, medium, low — only relevant for partial; based on element importance>"
    }
  ]
}"""

_SYSTEM_INSTRUCTIONS_FOOTER = """\

## Rules

1. Respond ONLY with the JSON object. No explanatory text before or after.
2. Assess ONLY the elements provided in the input. Do not add assessments for \
elements not present in the matched elements list.
3. The "severity" field for partial elements should reflect the importance of the \
expected element: high for elements that define the document's core purpose or scope, \
medium for elements that support understanding but are not structural, low for \
supplementary elements.
4. The "description" field for partial elements must describe what additional content \
is expected — be specific and actionable.
5. Do not include any information about users, sessions, accounts, or metadata not \
present in the document content itself.
6. Base your assessment solely on the Knowledge Model elements and the schema definition \
provided — do not introduce external expectations.\
"""


def build(elements_json: str, schema_json: str, response_language: str = "Spanish") -> str:
    """Construct the completeness evaluation prompt from KM elements and schema.

    This prompt is used for partial coverage assessment: given elements that
    exist in the Knowledge Model, determine if they adequately cover their
    schema definition or only partially address it.

    Args:
        elements_json: JSON string of Knowledge Model elements that have been
            matched to expected schema elements. Contains only element content
            and metadata — no user information (Req 9.2, 10.7).
        schema_json: JSON string of the document type schema defining expected
            elements and their descriptions. Must be included for the LLM to
            compare coverage against expectations (Req 10.4).
        response_language: Full language name for the LLM response (e.g.
            "Spanish", "English"). Defaults to "Spanish".

    Returns:
        The complete prompt string ready to send to the LLM.
    """
    instructions = _SYSTEM_INSTRUCTIONS + _JSON_SCHEMA + _SYSTEM_INSTRUCTIONS_FOOTER

    return f"""Respond in {response_language}.

{instructions}

--- DOCUMENT TYPE SCHEMA ---
{schema_json}
--- END DOCUMENT TYPE SCHEMA ---

--- MATCHED KNOWLEDGE MODEL ELEMENTS ---
{elements_json}
--- END MATCHED KNOWLEDGE MODEL ELEMENTS ---"""
