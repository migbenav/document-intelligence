"""Versioned prompt template for Questions Answered v2 analysis.

Instructs the LLM to reveal the document's LOGICAL CHAIN — adapted to the
document classification — rather than listing what each section talks about.
Includes coherence assessment when the document lacks a clear logical structure.

Requirements covered: Req 2 (criteria 1-9)
"""

PROMPT_VERSION = "questions-answered-v2"

_CLASSIFICATION_INSTRUCTIONS = {
    "normative": (
        "Identify the REGULATORY LOGIC: "
        "What does it regulate? What is permitted? What is prohibited? "
        "Who enforces? What are consequences?"
    ),
    "procedure": (
        "Identify the PROCESS LOGIC: "
        "Can it be done? Who decides? How is it executed? How is it controlled?"
    ),
    "narrative": (
        "Identify the NARRATIVE LOGIC: "
        "What is the subject? What sequence does it follow? "
        "What conclusion is reached?"
    ),
    "generic": (
        "Identify the FUNCTIONAL LOGIC: "
        "What does this document establish and how does it organize that purpose?"
    ),
}

PROMPT_TEMPLATE = """\
Respond in {response_language}.

This is a {classification} document.

{classification_instructions}

Analyze the following document and identify what questions it answers. The \
questions must reveal the LOGICAL CHAIN of the document — not describe what \
each section says.

## Document-Level Questions (3-5)

Identify 3 to 5 questions that reveal the document's logical chain or coverage. \
These questions should expose the PURPOSE FLOW of the document — what it \
establishes, enables, restricts, or controls — adapted to its classification.

Good questions reveal logic:
- "Who is authorized to approve expenses above the monthly threshold?"
- "What sequence of steps converts a purchase request into a paid order?"
- "What restrictions apply before a unit modification can begin?"

Bad questions describe content:
- "What does chapter 3 cover?"
- "What is discussed in the introduction?"
- "What topics are mentioned in the annexes?"

## Section-Level Questions (1-2 per major section)

For each major section, identify 1 to 2 questions that reveal what that section \
CONTRIBUTES to the document's logical chain. Each section-level question should \
connect to the document's overall logic.

## Rules

- Questions MUST be well-formed questions in {response_language}.
- Questions MUST be SPECIFIC and reveal PURPOSE — never generic.
- Questions must follow the logical chain appropriate to this document type.
- Do NOT produce questions that simply describe what a section "talks about."
- Each question must include a source_ref with the chunk_ids and text excerpt \
that answers it.
- Document-level questions should trace the document's logical flow.
- Section-level questions should show how each part contributes to that flow.
- If the document does not have a coherent logic (disconnected sections, no \
clear purpose flow), include a coherence_note explaining why the logical chain \
is weak or absent.

--- DOCUMENT CONTENT ---
{document_text}
--- END DOCUMENT ---

Respond ONLY with a JSON object matching this schema:
{{
  "document_questions": [
    {{
      "question": "<question revealing the document's logical chain>",
      "level": "document",
      "section_title": null,
      "source_ref": {{
        "chunk_ids": ["<IR chunk ID(s) where the answer is found>"],
        "text_excerpt": "<verbatim text excerpt (max 500 chars) that answers this question>",
        "section": "<section name where the excerpt appears>"
      }}
    }}
  ],
  "section_questions": [
    {{
      "question": "<question revealing what this section contributes to the logical chain>",
      "level": "section",
      "section_title": "<title of the section>",
      "source_ref": {{
        "chunk_ids": ["<IR chunk ID(s) where the answer is found>"],
        "text_excerpt": "<verbatim text excerpt (max 500 chars) that answers this question>",
        "section": "<section name where the excerpt appears>"
      }}
    }}
  ],
  "coherence_note": "<optional: explanation of why the document lacks a coherent logical chain, or null if coherent>"
}}
"""


def get_classification_instructions(classification: str) -> str:
    """Return classification-specific instructions for the prompt.

    Falls back to 'generic' if the classification is not recognized.
    """
    return _CLASSIFICATION_INSTRUCTIONS.get(
        classification, _CLASSIFICATION_INSTRUCTIONS["generic"]
    )


def format_prompt(
    classification: str,
    response_language: str,
    document_text: str,
) -> str:
    """Format the questions answered v2 prompt with all placeholders filled."""
    classification_instructions = get_classification_instructions(classification)
    return PROMPT_TEMPLATE.format(
        classification=classification,
        classification_instructions=classification_instructions,
        response_language=response_language,
        document_text=document_text,
    )
