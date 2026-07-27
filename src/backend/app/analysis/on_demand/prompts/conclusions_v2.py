"""Versioned prompt template for Conclusions v2 — Domain-Aware Coherence.

This redesigned prompt instructs the LLM to:
1. Identify independent domains/topics in the document
2. Evaluate structural coherence WITHIN each domain
3. Never flag contradictions between independent domains
4. Adapt evaluation criteria based on document classification

New categories: purpose_mismatch, misplaced_content, title_mismatch,
sequence_issue, duplication, contradiction.

Requirements covered: Req 3 (criteria 1-10)
"""

PROMPT_VERSION = "conclusions-v2"

PROMPT_TEMPLATE = """\
Respond in {response_language} for descriptions. Write suggestions in {document_language}.

This is a {classification} document.

Analyze the following document's structural coherence using a domain-aware approach.

## Step 1: Identify the INDEPENDENT DOMAINS/TOPICS in this document

Before evaluating issues, identify the distinct domains or topics the document \
addresses (e.g., parking, elevators, common areas, budgeting, hiring). Each \
domain is a coherent thematic area that operates independently from others.

## Step 2: For each domain and for the document as a whole, evaluate:

1. **Purpose Mismatch** (purpose_mismatch): Does each section's PURPOSE match \
the document type? For example, a procedural paragraph inside a normative \
document, or regulatory content in a user guide.

2. **Misplaced Content** (misplaced_content): Is each paragraph in the RIGHT \
PLACE by semantic affinity? Content that would be better located in a different \
section based on topic distance and logical grouping.

3. **Title Mismatch** (title_mismatch): Do TITLES reflect their actual content? \
Headings that do not accurately represent what the section contains.

4. **Sequence Issue** (sequence_issue): Is the ORDER logical? Content that \
appears in an illogical order (e.g., prerequisites described after execution \
steps, definitions placed after the sections that use them).

5. **Duplication** (duplication): Is there DUPLICATED content? Information that \
appears repeated across multiple sections, either verbatim or in substance.

6. **Contradiction** (contradiction): Are there CONTRADICTIONS within the SAME \
domain? Conflicting rules, statements, or definitions that address the same \
topic area.

## CRITICAL RULES

- **NEVER flag contradictions between INDEPENDENT domains.** Parking rules and \
elevator rules are different domains — they cannot contradict each other. \
Different policies for different areas are expected and normal.
- Contradictions are ONLY valid between sections that address the SAME domain/topic.
- For narrative documents: focus on logical sequence and narrative coherence, \
not purpose compliance. Evaluate whether the narrative flows logically and \
reaches its conclusion coherently.
- Suggestions must be STRUCTURAL ONLY: move, split, merge, rename, add, or \
remove a section. Never suggest what the text content should say.
- Every observation must have a source_ref with at least one chunk_id and a text_excerpt.
- Produce between 3 and 15 observations, prioritized by structural impact.
- Focus on significant issues — exclude trivial or obvious observations.
- Do not invent structural problems that do not exist in the document.

--- DOCUMENT CONTENT ---
{document_text}
--- END DOCUMENT ---

Respond ONLY with a JSON object matching this schema:
{{
  "domains_identified": ["string — each independent domain/topic found in the document"],
  "observations": [
    {{
      "category": "purpose_mismatch | misplaced_content | title_mismatch | sequence_issue | duplication | contradiction",
      "description": "string (in {response_language}) — explain WHAT the issue is and WHY it matters",
      "suggestion": "string (in {document_language}) — structural action: move, split, merge, rename, add, or remove",
      "section_ref": "string or null — section title/identifier the observation refers to",
      "domain": "string or null — which domain this observation belongs to (from domains_identified)",
      "source_ref": {{
        "chunk_ids": ["string"],
        "text_excerpt": "string (max 500 chars)",
        "section": "string"
      }}
    }}
  ]
}}
"""
