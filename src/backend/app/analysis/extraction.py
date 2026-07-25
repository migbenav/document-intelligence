"""Knowledge Model extraction service.

Extracts a structured Knowledge Model from the Intermediate Representation
using the primary LLM model. Handles parsing, post-processing (dangling
references, bidirectional contradicts, output normalization), and segmentation
for large documents.

Requirements covered: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.4, 6.5, 10.1
"""

import json
import logging
from datetime import datetime, timezone

from app.analysis.llm_client import LLMClient, LLMResponse
from app.analysis.prompts import extraction_v1
from app.models.document import DocumentFormat, IntermediateRepresentation
from app.models.knowledge_model import (
    ExtractionMetadata,
    KnowledgeElement,
    KnowledgeModel,
    Relation,
    SourceRef,
)

logger = logging.getLogger(__name__)

# Maximum total text size (in characters) before segmentation kicks in (Req 5.7)
_MAX_SEGMENT_CHARS = 100_000

# Default temperature for extraction calls
_DEFAULT_TEMPERATURE = 0.1


class ExtractionError(Exception):
    """Raised when the LLM response cannot be parsed at all (complete parse failure).

    Signals the pipeline to halt and mark the session as failed (Req 5.6).
    """

    pass


class ExtractionService:
    """Extracts a Knowledge Model from the IR using the primary LLM.

    The service constructs prompts from the versioned template, calls the LLM,
    parses and validates the response, and applies post-processing to ensure
    relationship integrity and output normalization.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def extract(
        self, ir: IntermediateRepresentation, document_type: str
    ) -> KnowledgeModel:
        """Extract a Knowledge Model from the IR.

        Args:
            ir: The Intermediate Representation of the document.
            document_type: The confirmed document type (prd, technical_spec,
                policy_process, or generic).

        Returns:
            A validated and post-processed KnowledgeModel.

        Raises:
            ExtractionError: When the LLM response cannot be parsed at all
                (complete parse failure — Req 5.6).
        """
        # Determine total text size for segmentation decision
        total_text = self._build_full_text(ir)

        if len(total_text) > _MAX_SEGMENT_CHARS:
            elements = await self._extract_segmented(ir, document_type)
        else:
            elements = await self._extract_single(ir, document_type, total_text)

        # Post-processing pipeline
        elements = self._normalize_output(elements)
        elements = self._populate_source_refs(elements, ir)
        elements = self._remove_dangling_references(elements)
        elements = self._ensure_bidirectional_contradicts(elements)
        self._validate_proposito(elements)

        # Count relationships
        relationship_count = sum(len(e.relations) for e in elements)

        # Build extraction metadata
        metadata = ExtractionMetadata(
            prompt_version=extraction_v1.VERSION,
            model_id=self._last_model_id,
            temperature=_DEFAULT_TEMPERATURE,
            element_count=len(elements),
            relationship_count=relationship_count,
            verification_rate=0.0,  # Set later by VerificationService
            extracted_at=datetime.now(timezone.utc),
        )

        return KnowledgeModel(
            document_id=ir.document_id,
            document_type=document_type,
            elements=elements,
            extraction_metadata=metadata,
        )

    async def _extract_single(
        self,
        ir: IntermediateRepresentation,
        document_type: str,
        ir_text: str,
    ) -> list[KnowledgeElement]:
        """Extract elements from the full IR in a single LLM call."""
        structural_contexts = self._build_structural_contexts(ir)
        prompt = extraction_v1.build(ir_text, document_type, structural_contexts)

        response = await self._llm_client.call(
            prompt, model_tier="primary", temperature=_DEFAULT_TEMPERATURE
        )
        self._last_model_id = response.model_id

        return self._parse_response(response.content, ir.document_id)

    async def _extract_segmented(
        self, ir: IntermediateRepresentation, document_type: str
    ) -> list[KnowledgeElement]:
        """Extract elements from a large document by splitting at chunk boundaries.

        Segments the IR into chunks that fit within the context limit,
        calls the LLM for each segment, and merges results with deduplication
        by element name + type (Req 5.7).
        """
        segments = self._create_segments(ir)
        all_elements: list[KnowledgeElement] = []
        self._last_model_id = ""

        for segment_chunks in segments:
            segment_ir = IntermediateRepresentation(
                document_id=ir.document_id,
                metadata=ir.metadata,
                chunks=segment_chunks,
            )
            segment_text = self._build_full_text(segment_ir)
            structural_contexts = self._build_structural_contexts(segment_ir)
            prompt = extraction_v1.build(segment_text, document_type, structural_contexts)

            response = await self._llm_client.call(
                prompt, model_tier="primary", temperature=_DEFAULT_TEMPERATURE
            )
            self._last_model_id = response.model_id

            segment_elements = self._parse_response(response.content, ir.document_id)
            all_elements.extend(segment_elements)

        # Deduplicate by (name_lower, type)
        return self._deduplicate_elements(all_elements)

    def _create_segments(self, ir: IntermediateRepresentation) -> list[list]:
        """Split IR chunks into segments that fit within the character limit."""
        segments: list[list] = []
        current_segment: list = []
        current_size = 0

        for chunk in sorted(ir.chunks, key=lambda c: c.order):
            chunk_size = len(chunk.text)
            if current_size + chunk_size > _MAX_SEGMENT_CHARS and current_segment:
                segments.append(current_segment)
                current_segment = []
                current_size = 0
            current_segment.append(chunk)
            current_size += chunk_size

        if current_segment:
            segments.append(current_segment)

        return segments

    def _deduplicate_elements(
        self, elements: list[KnowledgeElement]
    ) -> list[KnowledgeElement]:
        """Deduplicate elements by (name_lower, type), keeping the first occurrence."""
        seen: set[tuple[str, str]] = set()
        unique: list[KnowledgeElement] = []

        for elem in elements:
            key = (elem.name.strip().lower(), elem.type)
            if key not in seen:
                seen.add(key)
                unique.append(elem)

        return unique

    def _parse_response(
        self, content: str, document_id: str
    ) -> list[KnowledgeElement]:
        """Parse the LLM JSON response into KnowledgeElements.

        Raises ExtractionError on complete parse failure (Req 5.6).
        Discards individual malformed elements with warnings (Req 5.6).
        """
        # Strip potential markdown code fences
        cleaned = content.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (with optional language tag)
            first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
            cleaned = cleaned[first_newline + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as e:
            raise ExtractionError(
                f"Complete parse failure: LLM response is not valid JSON. Error: {e}"
            ) from e

        if not isinstance(data, dict) or "elements" not in data:
            raise ExtractionError(
                "Complete parse failure: Response JSON does not contain 'elements' key."
            )

        raw_elements = data.get("elements", [])
        if not isinstance(raw_elements, list):
            raise ExtractionError(
                "Complete parse failure: 'elements' field is not a list."
            )

        # Parse individual elements, discarding malformed ones
        valid_elements: list[KnowledgeElement] = []
        for i, raw_elem in enumerate(raw_elements):
            try:
                element = self._parse_element(raw_elem, document_id)
                valid_elements.append(element)
            except (KeyError, TypeError, ValueError) as e:
                logger.warning(
                    "Discarding malformed element at index %d: %s",
                    i,
                    str(e),
                    extra={"raw_element": str(raw_elem)[:200]},
                )

        return valid_elements

    def _parse_element(self, raw: dict, document_id: str) -> KnowledgeElement:
        """Parse a single raw element dict into a KnowledgeElement.

        Raises KeyError/TypeError/ValueError if the element is malformed.
        """
        if not isinstance(raw, dict):
            raise TypeError(f"Element is not a dict: {type(raw)}")

        # Required fields
        elem_id = raw["id"]
        elem_type = raw["type"]
        name = raw["name"]
        content_field = raw["content"]

        if not all(isinstance(f, str) for f in [elem_id, elem_type, name, content_field]):
            raise TypeError("Element fields must be strings")

        # Validate type against taxonomy
        valid_types = {"proposito", "concepto", "actor", "regla", "proceso", "restriccion"}
        if elem_type not in valid_types:
            raise ValueError(f"Invalid element type: {elem_type}")

        # Parse source_ref
        raw_source_ref = raw.get("source_ref", {})
        if not isinstance(raw_source_ref, dict):
            raise TypeError("source_ref must be a dict")

        source_ref = SourceRef(
            document_id=document_id,
            chunk_id=raw_source_ref.get("chunk_id", "unknown"),
            page=raw_source_ref.get("page"),
            section=raw_source_ref.get("section"),
            evidence=raw_source_ref.get("evidence", ""),
        )

        # Parse relations
        raw_relations = raw.get("relations", [])
        relations: list[Relation] = []
        if isinstance(raw_relations, list):
            for raw_rel in raw_relations:
                try:
                    rel = self._parse_relation(raw_rel)
                    relations.append(rel)
                except (KeyError, TypeError, ValueError) as e:
                    logger.warning(
                        "Discarding malformed relation in element %s: %s",
                        elem_id,
                        str(e),
                    )

        return KnowledgeElement(
            id=elem_id,
            type=elem_type,
            name=name,
            content=content_field,
            source_ref=source_ref,
            relations=relations,
        )

    def _parse_relation(self, raw: dict) -> Relation:
        """Parse a single raw relation dict into a Relation."""
        if not isinstance(raw, dict):
            raise TypeError(f"Relation is not a dict: {type(raw)}")

        target_id = raw["target_id"]
        rel_type = raw["type"]

        if not isinstance(target_id, str) or not isinstance(rel_type, str):
            raise TypeError("Relation fields must be strings")

        valid_rel_types = {"constrains", "participates_in", "depends_on", "contradicts"}
        if rel_type not in valid_rel_types:
            raise ValueError(f"Invalid relation type: {rel_type}")

        return Relation(
            target_id=target_id,
            type=rel_type,
            description=raw.get("description"),
        )

    def _normalize_output(
        self, elements: list[KnowledgeElement]
    ) -> list[KnowledgeElement]:
        """Apply output normalization to reduce non-determinism (Req 10.1).

        - Trim whitespace from names and content
        - Ensure types are lowercase
        """
        normalized: list[KnowledgeElement] = []
        for elem in elements:
            normalized_elem = elem.model_copy(
                update={
                    "name": elem.name.strip(),
                    "content": elem.content.strip(),
                    "type": elem.type.lower(),
                    "source_ref": elem.source_ref.model_copy(
                        update={"evidence": elem.source_ref.evidence.strip()}
                    ),
                }
            )
            normalized.append(normalized_elem)
        return normalized

    def _populate_source_refs(
        self, elements: list[KnowledgeElement], ir: IntermediateRepresentation
    ) -> list[KnowledgeElement]:
        """Populate format-specific source_ref fields (Req 5.5).

        - PDF: populate page from structural_context
        - Markdown: populate section from structural_context
        """
        doc_format = ir.metadata.format

        # Build a lookup of chunk_id -> structural_context
        chunk_context_map: dict[str, dict] = {
            chunk.chunk_id: chunk.structural_context for chunk in ir.chunks
        }

        updated: list[KnowledgeElement] = []
        for elem in elements:
            chunk_ctx = chunk_context_map.get(elem.source_ref.chunk_id, {})

            source_ref_updates: dict = {}
            if doc_format == DocumentFormat.PDF:
                page = chunk_ctx.get("page") or elem.source_ref.page
                source_ref_updates["page"] = page
            elif doc_format == DocumentFormat.MARKDOWN:
                section = chunk_ctx.get("section") or elem.source_ref.section
                source_ref_updates["section"] = section

            if source_ref_updates:
                updated_ref = elem.source_ref.model_copy(update=source_ref_updates)
                elem = elem.model_copy(update={"source_ref": updated_ref})

            updated.append(elem)

        return updated

    def _remove_dangling_references(
        self, elements: list[KnowledgeElement]
    ) -> list[KnowledgeElement]:
        """Remove relationships that reference non-existent element IDs (Req 6.5)."""
        valid_ids = {elem.id for elem in elements}
        result: list[KnowledgeElement] = []

        for elem in elements:
            valid_relations = [
                rel for rel in elem.relations if rel.target_id in valid_ids
            ]
            if len(valid_relations) != len(elem.relations):
                removed_count = len(elem.relations) - len(valid_relations)
                logger.warning(
                    "Removed %d dangling reference(s) from element %s",
                    removed_count,
                    elem.id,
                )
                elem = elem.model_copy(update={"relations": valid_relations})
            result.append(elem)

        return result

    def _ensure_bidirectional_contradicts(
        self, elements: list[KnowledgeElement]
    ) -> list[KnowledgeElement]:
        """Ensure 'contradicts' relationships are bidirectional (Req 6.4).

        If element A contradicts B, B must also reference A.
        """
        # Build element lookup by ID
        elem_map: dict[str, KnowledgeElement] = {elem.id: elem for elem in elements}

        # Collect all contradicts pairs
        contradicts_pairs: set[tuple[str, str]] = set()
        for elem in elements:
            for rel in elem.relations:
                if rel.type == "contradicts":
                    contradicts_pairs.add((elem.id, rel.target_id))

        # Ensure reverse direction exists
        for source_id, target_id in contradicts_pairs:
            if target_id not in elem_map:
                continue

            target_elem = elem_map[target_id]
            # Check if reverse already exists
            has_reverse = any(
                rel.target_id == source_id and rel.type == "contradicts"
                for rel in target_elem.relations
            )

            if not has_reverse:
                # Add reverse relationship
                reverse_rel = Relation(
                    target_id=source_id,
                    type="contradicts",
                    description=None,
                )
                updated_relations = list(target_elem.relations) + [reverse_rel]
                elem_map[target_id] = target_elem.model_copy(
                    update={"relations": updated_relations}
                )

        return list(elem_map.values())

    def _validate_proposito(self, elements: list[KnowledgeElement]) -> None:
        """Validate that at minimum a 'proposito' element exists (Req 5.3).

        Logs a warning if missing — does not halt extraction.
        """
        has_proposito = any(elem.type == "proposito" for elem in elements)
        if not has_proposito:
            logger.warning(
                "Knowledge Model does not contain a 'proposito' element. "
                "Every document should have at least one purpose element."
            )

    def _build_full_text(self, ir: IntermediateRepresentation) -> str:
        """Concatenate all IR chunk texts in order."""
        sorted_chunks = sorted(ir.chunks, key=lambda c: c.order)
        return "\n".join(chunk.text for chunk in sorted_chunks)

    def _build_structural_contexts(
        self, ir: IntermediateRepresentation
    ) -> list[dict]:
        """Build structural context list from IR chunks for the prompt."""
        contexts: list[dict] = []
        for chunk in sorted(ir.chunks, key=lambda c: c.order):
            ctx = {"chunk_id": chunk.chunk_id}
            ctx.update(chunk.structural_context)
            contexts.append(ctx)
        return contexts
