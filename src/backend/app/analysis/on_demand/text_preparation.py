"""Shared text preparation utility for on-demand analyzers.

Converts the document's IntermediateRepresentation into a single string
suitable for inclusion in LLM prompts. All four on-demand analyzers use
this function to build the document context section of their prompts.
"""

from app.models.document import IntermediateRepresentation


def prepare_document_text(ir: IntermediateRepresentation) -> str:
    """Concatenate IR chunks with section markers for LLM prompt inclusion.

    Produces a formatted string where each chunk is annotated with its
    section name and order position, preserving the document's reading
    sequence. Chunks are sorted by their ``order`` field.

    Format per chunk::

        [Section: {section}] (chunk {order})
        {text}

    Args:
        ir: The document's IntermediateRepresentation containing ordered
            content chunks with structural context.

    Returns:
        A single string with all chunks formatted with section markers,
        separated by blank lines.
    """
    sorted_chunks = sorted(ir.chunks, key=lambda c: c.order)
    parts: list[str] = []

    for chunk in sorted_chunks:
        section = chunk.structural_context.get("section") or "Untitled"
        header = f"[Section: {section}] (chunk {chunk.order})"
        parts.append(f"{header}\n{chunk.text}")

    return "\n\n".join(parts)
