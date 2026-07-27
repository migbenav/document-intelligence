"""Versioned prompt template for Build Index v2 — Functional Comprehension.

Instructs the LLM to analyze a document's FUNCTIONAL ORGANIZATION rather than
its visual heading structure. The prompt asks the model to identify what each
part of the document DOES (its purpose) and group sections by function, not
by chapter or heading layout.

The prompt adapts to document classification (normative, procedure, narrative,
generic) through purpose hints that guide the model's understanding.

Requirements covered: Req 1 (criteria 1-8)
"""

PROMPT_VERSION = "build-index-v2"

# Classification-specific purpose hints
_PURPOSE_HINTS: dict[str, str] = {
    "normative": "establish rules, obligations, and compliance requirements",
    "procedure": "describe steps, workflows, and operational processes",
    "narrative": "convey a story, report events, or present a sequence of ideas",
    "technical": "document specifications, architectures, or technical systems",
    "informative": "provide information, explanations, or educational content",
    "generic": "organize and communicate structured information",
}


def get_purpose_hint(classification: str) -> str:
    """Return the purpose hint for a given classification, defaulting to generic."""
    return _PURPOSE_HINTS.get(classification, _PURPOSE_HINTS["generic"])


PROMPT_TEMPLATE = """\
Respond in {response_language}.

You are analyzing a {classification} document. Its purpose is to \
{purpose_hint}.

## Your Task

Analyze this document in TWO steps:

### Step 1: Identify the document's OVERALL PURPOSE in one sentence.

State what this document exists to DO — its function as an instrument.

### Step 2: Identify FUNCTIONAL GROUPINGS

Identify how the document organizes its functions. Do NOT simply list headings. \
Instead, determine what each part of the document DOES functionally.

**Key principles:**
- Multiple chapters or sections serving the same function belong in ONE functional node.
- The tree represents FUNCTION, not visual layout.
- For each node: describe what this part DOES functionally (not what it says).
- Group content by purpose: e.g., "Purpose and Scope", "Execution", "Control and Payment" \
— NOT by chapter number or heading text.

### For each node in the tree, provide:

1. **id**: A unique identifier (e.g., "node-1", "node-1.1").
2. **title**: A functional label describing what this grouping DOES (e.g., \
"Scope and Definitions", "Execution Process", "Oversight and Control"). This is NOT \
necessarily a heading from the document.
3. **level**: Hierarchy depth (1 = top-level functional group, max 6).
4. **role**: What this section DOES functionally. Use one of:
   - "defines" — introduces or defines terms, concepts, or scope
   - "classifies" — categorizes or groups items
   - "establishes" — sets up procedures, processes, or workflows
   - "enables" — permits, allows, or authorizes actions
   - "restricts" — imposes limitations, prohibitions, or boundaries
   - "controls" — monitors, verifies, or enforces compliance
   - "delegates" — assigns responsibility or authority to other actors
   - "regulates" — imposes rules or obligations
   - "recommends" — suggests non-mandatory guidance
   - "lists" — enumerates items or options
   - "describes" — provides explanatory or narrative content
5. **functional_group**: A short label identifying the functional grouping this node \
belongs to (e.g., "purpose", "execution", "control", "definitions"). Nodes that serve \
the same broad function share the same functional_group value.
6. **original_headings**: The ACTUAL chapter titles or headings from the document that \
were merged into this functional node. If a single heading maps 1:1, include it. If \
multiple headings were grouped, list all of them.
7. **question_answered**: The FUNCTIONAL CONTRIBUTION question — what role does this part \
play? (e.g., "How is spending controlled?" or "What authorities are delegated?"). \
Do NOT write content summaries like "What does chapter 5 say?"
8. **source_ref**: Evidence reference containing:
   - "chunk_ids": list of IR chunk IDs where this content is found
   - "text_excerpt": a representative excerpt (max 500 characters)
   - "section": the original section heading from the document
9. **children**: Sub-nodes for finer functional breakdowns. Empty array if no \
sub-functions exist.

## Rules

- The first level of the tree represents MAJOR FUNCTIONAL AREAS, not chapters.
- Preserve document order within functional groupings.
- Maximum depth is 6 levels.
- Every node must have a source_ref with at least one chunk_id and a text_excerpt.
- Do NOT invent content that doesn't exist in the document.
- Do NOT create a node for every heading — merge related headings into functional groups.
- Be thorough: cover all document content, but organize it by function.

--- DOCUMENT CONTENT ---
{document_text}
--- END DOCUMENT ---

Respond ONLY with a JSON object matching this schema:
{{
  "document_purpose": "string (one sentence: what this document exists to DO)",
  "tree": [
    {{
      "id": "string",
      "title": "string (functional label)",
      "level": 1,
      "role": "string or null",
      "functional_group": "string (grouping label)",
      "original_headings": ["string (actual document headings merged here)"],
      "question_answered": "string or null (functional contribution question)",
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
