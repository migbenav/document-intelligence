"""Versioned prompt template for Build Index analysis (C3.1).

Instructs the LLM to analyze document structure and produce a hierarchical tree
of sections. Each node identifies its functional role and the question the
section answers, following a cascade from document purpose to section objectives.

Requirements covered: Req 2 (criteria 1-6)
"""

PROMPT_VERSION = "build-index-v1"

PROMPT_TEMPLATE = """\
Respond in {response_language}.

Analyze the following document and produce a hierarchical tree of its sections \
and subsections (structure_tree). For each node in the tree, provide:

1. **id**: A unique identifier for the node (e.g., "node-1", "node-1.1", "node-1.1.2").
2. **title**: The section heading as it appears in the document, or an inferred \
label if no explicit heading exists.
3. **level**: The hierarchy depth (1 = top-level section, 2 = subsection, etc.). \
Maximum depth is 6 — flatten any deeper nesting to level 6.
4. **role**: What this section DOES functionally. Use one of these values, or null \
if the role cannot be determined:
   - "defines" — introduces or defines terms, concepts, or scope
   - "classifies" — categorizes or groups items
   - "establishes" — sets up procedures, processes, or workflows
   - "regulates" — imposes rules, obligations, or compliance requirements
   - "recommends" — suggests best practices or non-mandatory guidance
   - "lists" — enumerates items, options, or elements
   - "restricts" — imposes limitations, prohibitions, or boundaries
   - "describes" — provides explanatory or narrative content
5. **question_answered**: The question this section answers in the document's \
knowledge cascade. Follow this pattern:
   - Level 1 nodes answer broad questions about the document's overall purpose \
(e.g., "How is procurement managed in this organization?")
   - Deeper levels answer progressively more specific questions about their \
parent's scope (e.g., "What steps apply when requesting a purchase with return?")
   - If no meaningful question can be inferred, set to null.
6. **source_ref**: Evidence reference containing:
   - "chunk_ids": list of IR chunk IDs where this section's content is found
   - "text_excerpt": a representative excerpt from the section (max 500 characters)
   - "section": the section name/heading as it appears in the document
7. **children**: An array of child nodes (recursive structure). Empty array if \
the node has no subsections.

## Rules

- Preserve the document's original ordering — nodes must appear in document order.
- Maximum depth is 6 levels. If the document has deeper nesting, flatten to level 6.
- The role identifies what a section DOES functionally, not what it contains.
- Every node must have a source_ref with at least one chunk_id and a text_excerpt.
- Be thorough: include all identifiable sections, not just major headings.
- Do not invent sections that do not exist in the document.

--- DOCUMENT CONTENT ---
{document_text}
--- END DOCUMENT ---

Respond ONLY with a JSON object matching this schema:
{{
  "tree": [
    {{
      "id": "string",
      "title": "string",
      "level": 1,
      "role": "string or null",
      "question_answered": "string or null",
      "source_ref": {{
        "chunk_ids": ["string"],
        "text_excerpt": "string (max 500 chars)",
        "section": "string"
      }},
      "children": []
    }}
  ]
}}
"""
