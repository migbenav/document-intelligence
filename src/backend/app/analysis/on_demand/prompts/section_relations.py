"""Versioned prompt template for Section Relations analysis (C3.2).

Instructs the LLM to identify significant relationships between document
sections using the vocabulary: constrains, depends_on, complements, contradicts.

Requirements covered: Req 3 (criteria 1-5)
"""

PROMPT_VERSION = "section-relations-v1"

PROMPT_TEMPLATE = """\
Respond in {response_language}.

Analyze the document below and identify significant relationships between its sections.

## Relationship Types

Use ONLY these relationship types:
- constrains: The source section limits or restricts the target section's scope, applicability, or interpretation.
- depends_on: The source section requires the target section to be understood first; it references concepts, definitions, or processes defined there.
- complements: The source section expands on the same topic as the target section, providing additional detail, examples, or alternative perspectives.
- contradicts: The source section contains content that conflicts with or is inconsistent with the target section.

## Instructions

1. Focus on explicit references between sections (cross-references, "as defined in...", "subject to...").
2. Identify implicit dependencies where one section assumes knowledge from another.
3. Find complementary sections that expand on the same topic from different angles.
4. Flag contradictions where sections provide conflicting information or requirements.
5. Exclude trivial connections — sequential order is NOT a relationship. "Section 2 follows Section 1" is not meaningful.
6. Focus on the most important connections. For most documents, 5-30 relationships is appropriate.
7. Each relationship must include a source_ref with the text excerpt that evidences the connection.

--- DOCUMENT CONTENT ---
{document_text}
--- END DOCUMENT ---

Respond ONLY with a JSON object matching this schema:
{{
  "relations": [
    {{
      "source_section": "<title or identifier of the originating section>",
      "target_section": "<title or identifier of the related section>",
      "type": "<one of: constrains, depends_on, complements, contradicts>",
      "description": "<one-sentence explanation of the relationship>",
      "source_ref": {{
        "chunk_ids": ["<IR chunk ID(s) where evidence was found>"],
        "text_excerpt": "<verbatim text excerpt (max 500 chars) evidencing this relationship>",
        "section": "<section name where the evidence appears>"
      }}
    }}
  ]
}}
"""
