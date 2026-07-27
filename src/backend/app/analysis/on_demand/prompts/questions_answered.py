"""Versioned prompt template for Questions Answered analysis (C3.3).

Instructs the LLM to identify what questions the document answers, organized
in a cascade: document-level (3-5 broad scope questions) and section-level
(1-2 per major section, more specific).

Requirements covered: Req 4 (criteria 1-6)
"""

PROMPT_VERSION = "questions-answered-v1"

PROMPT_TEMPLATE = """\
Respond in {response_language}.

Analyze the following document and identify what questions it answers. Organize \
the questions in a cascade with two levels:

## Document-Level Questions (3-5)

Identify 3 to 5 broad questions that the document as a whole addresses. These \
describe the document's overall purpose and scope — what someone would understand \
after reading the entire document.

Examples of good document-level questions:
- "Who is responsible for common area maintenance?"
- "How is the procurement process managed in this organization?"
- "What rules govern modifications to individual units?"

## Section-Level Questions (1-2 per major section)

For each major section or chapter, identify 1 to 2 specific questions that the \
section answers. These are more focused than document-level questions and describe \
what each section contributes to the document's purpose.

Examples of good section-level questions:
- "What steps must be followed to request a purchase with return?"
- "What restrictions apply to unit modifications?"
- "Who approves expenses above the monthly threshold?"

## Rules

- Questions MUST be well-formed questions in {response_language}.
- Questions MUST be specific and actionable — directly tied to the document's content.
- Do NOT use generic questions like "What does this section cover?" or "What is \
discussed here?"
- Each question must include a source_ref with the chunk_ids and text excerpt \
that answers it.
- Document-level questions should be broader in scope than section-level questions.
- Section-level questions should NOT be more general than document-level questions.

--- DOCUMENT CONTENT ---
{document_text}
--- END DOCUMENT ---

Respond ONLY with a JSON object matching this schema:
{{
  "document_questions": [
    {{
      "question": "<well-formed question describing what the whole document addresses>",
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
      "question": "<well-formed question describing what this section answers>",
      "level": "section",
      "section_title": "<title of the section that answers this question>",
      "source_ref": {{
        "chunk_ids": ["<IR chunk ID(s) where the answer is found>"],
        "text_excerpt": "<verbatim text excerpt (max 500 chars) that answers this question>",
        "section": "<section name where the excerpt appears>"
      }}
    }}
  ]
}}
"""
