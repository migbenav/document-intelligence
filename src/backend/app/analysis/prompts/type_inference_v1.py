"""Versioned prompt template for document type classification.

Instructs the LLM to classify a document as one of the supported types
based on a sample of the document's IR text content.

Requirements covered: 2.1, 2.2, 2.4, 3.1
"""

VERSION = "type-inference-v1"

_VALID_TYPES = ("prd", "technical_spec", "policy_process", "generic")

_SYSTEM_INSTRUCTIONS = """\
You are a document type classifier. Analyze the provided document text sample \
and classify it into exactly one of the following types:

- prd: A Product Requirements Document containing user stories, acceptance criteria, \
feature descriptions, product goals, or stakeholder requirements.
- technical_spec: A Technical Specification containing API definitions, architecture \
descriptions, system design, data models, or implementation details.
- policy_process: A Policy or Process Document containing organizational policies, \
standard operating procedures, compliance rules, or workflow definitions.
- generic: A document that does not clearly fit any of the above categories.

Instructions:
1. Read the document text sample carefully.
2. Identify structural and content cues that indicate the document type.
3. Choose the single most appropriate type from the list above.
4. Provide a brief one-sentence justification explaining why you chose this type.

You MUST respond with valid JSON in exactly this format:
{"document_type": "<type>", "justification": "<one sentence explanation>"}

Do not include any other text outside the JSON object.\
"""


def build(ir_text_sample: str) -> str:
    """Construct the type inference prompt from a document text sample.

    Args:
        ir_text_sample: The first ~2000 characters of the IR text content.
            Should contain only document text and structural context (headings,
            section markers). Must NOT contain user metadata or session info (Req 2.4).

    Returns:
        The complete prompt string ready to send to the LLM.
    """
    return f"""{_SYSTEM_INSTRUCTIONS}

--- DOCUMENT TEXT SAMPLE ---
{ir_text_sample}
--- END DOCUMENT TEXT SAMPLE ---"""
