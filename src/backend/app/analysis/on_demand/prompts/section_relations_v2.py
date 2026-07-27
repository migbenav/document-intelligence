"""Versioned prompt template for Section Relations v2 — Functional Connections.

Instructs the LLM to identify FUNCTIONAL relationships between document
sections using purpose-driven vocabulary: enables, restricts, requires,
implements, contradicts. Excludes trivial sequential relationships.

The prompt receives the document classification and, when available,
the Build Index structure tree to use functional group names as references.

Requirements covered: Req 4 (criteria 1-6)
"""

PROMPT_VERSION = "section-relations-v2"

PROMPT_TEMPLATE = """\
Respond in {response_language}.

This is a {classification} document.

Identify FUNCTIONAL relationships between document sections:

## Relationship Types

Use ONLY these relationship types:
- enables: one section permits/allows what another regulates.
- restricts: one section limits what another enables.
- requires: one section is a prerequisite for another.
- implements: one section details/operationalizes what another declares.
- contradicts: conflicting content within the SAME domain (never cross-domain).

## Instructions

1. Focus on how sections FUNCTIONALLY DEPEND on each other — what enables, restricts, or requires what.
2. For "implements": look for sections that operationalize abstract declarations (e.g., a procedure that implements a policy).
3. For "contradicts": ONLY flag conflicts between sections addressing the SAME topic/domain. Sections about different domains (e.g., parking rules vs elevator rules) are NEVER contradictory.
4. EXCLUDE trivial relationships: sequential order, adjacency, or "section B follows section A" are NOT relationships.
5. If Build Index structure is available, use functional group names as references for source_section and target_section.
6. Focus on the most important connections. For most documents, 5-30 relationships is appropriate.
7. Each relationship must include a source_ref with the text excerpt that evidences the connection.
8. Include a domain field indicating which topic/area the relationship belongs to (e.g., "procurement", "parking", "governance").

{structure_context}\
--- DOCUMENT CONTENT ---
{document_text}
--- END DOCUMENT ---

Respond ONLY with a JSON object matching this schema:
{{
  "relations": [
    {{
      "source_section": "<title or functional group of the originating section>",
      "target_section": "<title or functional group of the related section>",
      "type": "<one of: enables, restricts, requires, implements, contradicts>",
      "description": "<one-sentence explanation of the functional relationship>",
      "domain": "<topic/domain this relationship belongs to, or null>",
      "source_ref": {{
        "chunk_ids": ["<IR chunk ID(s) where evidence was found>"],
        "text_excerpt": "<verbatim text excerpt (max 500 chars) evidencing this relationship>",
        "section": "<section name where the evidence appears>"
      }}
    }}
  ]
}}
"""


def build_structure_context(index_result) -> str:
    """Build the structure context section for the prompt.

    When index_result is available, produces a summary of the structure tree
    so the LLM can reference functional group names. When not available,
    returns an empty string.

    Args:
        index_result: An IndexResult instance with tree nodes, or None.

    Returns:
        A formatted string to insert as {structure_context} in the prompt.
    """
    if index_result is None:
        return ""

    lines = [
        "--- BUILD INDEX STRUCTURE (use these functional group names as references) ---"
    ]
    _collect_structure_lines(index_result.tree, lines, indent=0)
    lines.append("--- END STRUCTURE ---\n\n")
    return "\n".join(lines)


def _collect_structure_lines(nodes, lines: list[str], indent: int) -> None:
    """Recursively collect structure tree lines with indentation."""
    prefix = "  " * indent
    for node in nodes:
        group_info = ""
        if hasattr(node, "functional_group") and node.functional_group:
            group_info = f" [{node.functional_group}]"
        lines.append(f"{prefix}- {node.id}: \"{node.title}\"{group_info}")
        if node.children:
            _collect_structure_lines(node.children, lines, indent + 1)
