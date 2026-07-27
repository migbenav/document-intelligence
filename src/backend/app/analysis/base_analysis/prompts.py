"""Versioned prompt template for the base analysis LLM call.

The prompt instructs the LLM to respond with JSON only, producing a short
summary (2-3 lines), a classification from the fixed set of document types,
and a language confirmation/correction.

Data minimization (ADR-005, Req 3.7): only title, organization_type, and a text
sample are included. No user identity, session history, account metadata, or
document_id is sent to the LLM.
"""

PROMPT_VERSION = "base-analysis-v2"

PROMPT_TEMPLATE = """\
Respond in {response_language}.
You are a document analysis assistant. Analyze the following document excerpt and respond with JSON only.

Document title: {title}
Organization type: {organization_type}

--- BEGIN TEXT SAMPLE ---
{text_sample}
--- END TEXT SAMPLE ---

Respond with a JSON object containing exactly three fields:
1. "summary": A concise summary of 2-3 lines describing what this document is about and its objective.
2. "classification": One of the following categories that best describes the document type: "normative", "guide", "manual", "procedure", "technical", "narrative", "other".
3. "language": Also confirm or correct the detected document language. The system detected: {detected_language}. If incorrect, provide the correct ISO 639-1 code (e.g., "es", "en", "pt", "fr"). If the detection is correct, repeat the same code.

Respond ONLY with the JSON object. No additional text, no markdown formatting, no code fences.
"""
