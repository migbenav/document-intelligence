"""Versioned prompt template for Conclusions & Recommendations analysis (C3.4).

Instructs the LLM to analyze the document's structural coherence and produce
observations about organization quality. Each observation includes a category,
a description in the user's language, and a structural suggestion written in
the document's own language (since it references the document's terminology).

Suggestions are STRUCTURAL only (move, split, merge, add, remove section) —
NOT content text suggestions about what the document should say.

Requirements covered: Req 5 (criteria 1-5)
"""

PROMPT_VERSION = "conclusions-v1"

PROMPT_TEMPLATE = """\
Respond in {response_language} for descriptions. Write suggestions in {document_language}.

Analyze the following document's structural coherence and produce observations \
about its organization. For each observation, provide:

1. **category**: Exactly one of these five values:
   - "coherence" — purpose mixing; sections whose functional role is inconsistent \
with the document's stated type (e.g., a procedural section inside a normative \
document, or a regulatory section in a user guide).
   - "reordering" — sections that might benefit from different placement within \
the document's structure (e.g., definitions placed after the sections that use them).
   - "duplication" — content that appears repeated across multiple sections, \
either verbatim or in substance.
   - "orphan" — sections that don't connect to the document's main purpose or \
that lack clear relationship to surrounding content.
   - "missing" — structural elements typically expected for this document type \
but absent (e.g., a normative document without a scope section, a procedure \
without an exceptions clause).

2. **description**: An explanation of the observation in {response_language}. \
Describe WHAT the structural issue is and WHY it matters.

3. **suggestion**: A structural recommendation written in {document_language}. \
This MUST be a structural action — move, split, merge, add, or remove a section. \
It references the document's own section names and terminology. \
Example: "Consider moving this section before Chapter II since it defines terms \
used there." \
NOT: "This paragraph should mention X" or "Add content about Y."

4. **section_ref**: The title or identifier of the section(s) the observation \
refers to. Use null if it applies to the document as a whole.

5. **source_ref**: Evidence reference containing:
   - "chunk_ids": list of IR chunk IDs where the relevant content is found
   - "text_excerpt": a representative excerpt from the document (max 500 characters)
   - "section": the section name/heading as it appears in the document

## Rules

- Produce between 3 and 15 observations, prioritized by structural impact.
- Focus on significant issues — exclude trivial or obvious observations.
- Suggestions are STRUCTURAL ONLY: move, split, merge, add, remove section. \
Never suggest what the text content should say.
- Every observation must have a source_ref with at least one chunk_id and a text_excerpt.
- Descriptions are in {response_language}. Suggestions are in {document_language}.
- Do not invent structural problems that do not exist in the document.

--- DOCUMENT CONTENT ---
{document_text}
--- END DOCUMENT ---

Respond ONLY with a JSON object matching this schema:
{{
  "observations": [
    {{
      "category": "coherence | reordering | duplication | orphan | missing",
      "description": "string (in {response_language})",
      "suggestion": "string (in {document_language})",
      "section_ref": "string or null",
      "source_ref": {{
        "chunk_ids": ["string"],
        "text_excerpt": "string (max 500 chars)",
        "section": "string"
      }}
    }}
  ]
}}
"""
