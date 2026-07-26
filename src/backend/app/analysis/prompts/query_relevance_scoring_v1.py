"""Versioned prompt template for Knowledge Model element relevance scoring.

Instructs the LLM to score each Knowledge Model element's relevance to a
user's natural language question on a scale of 0–10.

Requirements covered: 2.1, 6.1
"""

VERSION = "query-relevance-scoring-v1"

_SYSTEM_INSTRUCTIONS = """\
You are a relevance scoring engine. Your task is to evaluate how relevant each \
Knowledge Model element is to the user's question.

## Scoring Scale

Score each element from 0 to 10:
- 0: Completely irrelevant — the element has no connection to the question.
- 1–3: Low relevance — tangential or very indirect connection.
- 4–6: Moderate relevance — related topic but not directly answering the question.
- 7–9: High relevance — directly related and likely useful for answering the question.
- 10: Essential — directly answers or is critical to answering the question.

## Scoring Criteria

Consider these factors when scoring:
- Semantic similarity between the question and the element's name and content.
- Whether the element contains information that would help answer the question.
- Whether the element's type (e.g., proceso, regla, actor) matches what the question asks about.
- Indirect relevance through relationships (e.g., a rule that constrains a process being asked about).

## Output Format

Respond ONLY with a valid JSON array. Each entry must have:
- "id": The element's identifier (exactly as provided in the input).
- "score": An integer from 0 to 10.

Example output:
[{"id": "elem-001", "score": 8}, {"id": "elem-002", "score": 3}]

## Rules

1. Score EVERY element provided — do not skip any.
2. Respond ONLY with the JSON array. No explanatory text before or after.
3. Scores must be integers between 0 and 10 inclusive.
4. Use the full range of scores — not everything should be high or low.
5. Base scores solely on relevance to the question — do not consider element quality or length.\
"""


def build(question: str, element_summaries: list[dict[str, str]]) -> str:
    """Construct the relevance scoring prompt.

    Args:
        question: The user's natural language question.
        element_summaries: List of dicts with keys 'id', 'type', 'name',
            'content_preview' (first 100 chars of content for each KM element).

    Returns:
        Prompt that asks the LLM to score each element 0–10 for relevance
        to the question. Output format: JSON array of {"id": "...", "score": N}
    """
    # Format element summaries into a readable list
    elements_section = _format_element_summaries(element_summaries)

    return f"""{_SYSTEM_INSTRUCTIONS}

--- QUESTION ---
{question}
--- END QUESTION ---

--- ELEMENTS TO SCORE ---
{elements_section}
--- END ELEMENTS ---"""


def _format_element_summaries(element_summaries: list[dict[str, str]]) -> str:
    """Format element summaries into a readable section for the prompt.

    Args:
        element_summaries: List of dicts with keys 'id', 'type', 'name',
            'content_preview'.

    Returns:
        Formatted string listing all elements with their metadata.
    """
    if not element_summaries:
        return "No elements provided."

    lines: list[str] = []
    for summary in element_summaries:
        elem_id = summary.get("id", "unknown")
        elem_type = summary.get("type", "unknown")
        elem_name = summary.get("name", "unnamed")
        content_preview = summary.get("content_preview", "")
        lines.append(
            f"- id={elem_id}, type={elem_type}, name=\"{elem_name}\", "
            f"content_preview=\"{content_preview}\""
        )

    return "\n".join(lines)
