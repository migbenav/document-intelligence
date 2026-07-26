"""Context construction for the natural language query pipeline.

Selects relevant Knowledge Model elements via LLM-based semantic scoring,
includes first-degree relational context (one hop), enforces token budget,
and produces the QueryContext used by the answer-generation prompt.

Requirements covered: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7
"""

import json
import logging
from typing import TYPE_CHECKING

from app.analysis.prompts import query_relevance_scoring_v1
from app.models.knowledge_model import KnowledgeModel
from app.models.document import IntermediateRepresentation
from app.models.query import QueryContext, QueryContextElement, QueryContextRelation

if TYPE_CHECKING:
    from app.analysis.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Selects relevant KM elements and constructs the query context.

    Uses LLM-based semantic scoring (light model tier) to rank elements,
    applies a max-element cap and token budget, and includes one-hop
    relational context from directly relevant elements.
    """

    def __init__(
        self,
        llm_client: "LLMClient",
        max_elements: int = 20,
        budget_ratio: float = 0.6,
    ) -> None:
        """Initialize the ContextBuilder.

        Args:
            llm_client: LLM client for relevance scoring calls.
            max_elements: Maximum number of directly relevant elements to select.
            budget_ratio: Fraction of context_window_tokens allocated to context
                (default 0.6 = 60%).
        """
        self._llm_client = llm_client
        self._max_elements = max_elements
        self._budget_ratio = budget_ratio

    async def build_context(
        self,
        question: str,
        knowledge_model: KnowledgeModel,
        ir: IntermediateRepresentation,
        context_window_tokens: int,
    ) -> QueryContext | None:
        """Build query context from KM elements.

        Returns None if no elements meet relevance criteria (zero elements
        with score > 0). On scoring LLM failure, falls back to including all
        elements up to the token budget without ranking.

        Args:
            question: The user's natural language question.
            knowledge_model: The completed Knowledge Model for the document.
            ir: The Intermediate Representation (IR) of the document.
            context_window_tokens: The model's total context window size in tokens.

        Returns:
            QueryContext with selected elements and relations, or None if no
            elements are relevant.
        """
        token_budget = int(context_window_tokens * self._budget_ratio)
        elements = knowledge_model.elements

        if not elements:
            return None

        # Score elements via LLM
        scored_elements = await self._score_elements(question, elements)

        # Filter elements with score > 0 as relevant
        relevant = [(elem, score) for elem, score in scored_elements if score > 0]

        if not relevant:
            return None

        # Sort by score descending, then prefer verified over unverified for ties
        relevant.sort(key=lambda x: (x[1], x[0].verified), reverse=True)

        # Cap at max_elements
        direct_elements = relevant[: self._max_elements]

        # Collect directly relevant element IDs
        direct_ids = {elem.id for elem, _ in direct_elements}

        # Include first-degree relationships (one hop only)
        relational_elements = self._collect_one_hop_relations(
            direct_elements, elements, direct_ids
        )

        # Build context elements and relations within token budget
        return self._assemble_context(
            direct_elements, relational_elements, direct_ids, token_budget
        )

    async def _score_elements(
        self,
        question: str,
        elements: list,
    ) -> list[tuple]:
        """Score all KM elements for relevance to the question.

        Uses a single LLM call with the light model tier. On failure,
        falls back to assigning all elements a score of 1 (include all
        up to budget).

        Returns:
            List of (element, score) tuples.
        """
        # Build element summaries for the scoring prompt
        element_summaries = [
            {
                "id": elem.id,
                "type": elem.type,
                "name": elem.name,
                "content_preview": elem.content[:100],
            }
            for elem in elements
        ]

        prompt = query_relevance_scoring_v1.build(question, element_summaries)

        try:
            response = await self._llm_client.call(
                prompt, model_tier="light", temperature=0.1
            )
            scores = self._parse_scoring_response(response.content, elements)
            return scores
        except Exception:
            logger.warning(
                "Scoring LLM call failed, falling back to include all elements",
                exc_info=True,
            )
            # Fallback: assign score 1 to all elements (no ranking)
            return [(elem, 1) for elem in elements]

    def _parse_scoring_response(
        self, raw_content: str, elements: list
    ) -> list[tuple]:
        """Parse the LLM scoring response as JSON array of {id, score}.

        Args:
            raw_content: Raw LLM output (expected JSON array).
            elements: The original KM elements for ID lookup.

        Returns:
            List of (element, score) tuples. Elements not found in the
            response receive a score of 0.
        """
        # Strip potential markdown code fences
        content = raw_content.strip()
        if content.startswith("```"):
            # Remove opening fence (possibly with language tag)
            first_newline = content.index("\n")
            content = content[first_newline + 1 :]
            # Remove closing fence
            if content.endswith("```"):
                content = content[: -3].strip()

        scores_data = json.loads(content)

        # Build lookup by ID
        score_by_id: dict[str, int] = {}
        for entry in scores_data:
            elem_id = entry.get("id", "")
            score = entry.get("score", 0)
            # Clamp to valid range
            score = max(0, min(10, int(score)))
            score_by_id[elem_id] = score

        # Map back to elements
        element_by_id = {elem.id: elem for elem in elements}
        result = []
        for elem in elements:
            score = score_by_id.get(elem.id, 0)
            result.append((elem, score))

        return result

    def _collect_one_hop_relations(
        self,
        direct_elements: list[tuple],
        all_elements: list,
        direct_ids: set[str],
    ) -> list:
        """Collect elements reachable in exactly one hop from direct elements.

        Only includes elements that are NOT already in the direct set.

        Returns:
            List of KnowledgeElement objects reachable via one hop.
        """
        element_by_id = {elem.id: elem for elem in all_elements}
        one_hop_ids: set[str] = set()

        for elem, _ in direct_elements:
            for relation in elem.relations:
                target_id = relation.target_id
                if target_id not in direct_ids and target_id in element_by_id:
                    one_hop_ids.add(target_id)

        return [element_by_id[eid] for eid in one_hop_ids]

    def _assemble_context(
        self,
        direct_elements: list[tuple],
        relational_elements: list,
        direct_ids: set[str],
        token_budget: int,
    ) -> QueryContext:
        """Assemble the final QueryContext within the token budget.

        Priority for trimming (reverse priority = trimmed first):
        1. Relational context elements (trimmed first)
        2. Lower-scored direct elements (trimmed second)

        Within each category, unverified elements are trimmed before verified.

        Args:
            direct_elements: List of (element, score) tuples, sorted by priority.
            relational_elements: List of one-hop elements.
            direct_ids: Set of directly relevant element IDs.
            token_budget: Maximum token count for assembled context.

        Returns:
            QueryContext with elements, relations, and token count.
        """
        # Build context elements for direct elements (already sorted by priority)
        context_elements: list[QueryContextElement] = []
        included_ids: set[str] = set()

        # Add direct elements within budget
        current_tokens = 0
        for elem, score in direct_elements:
            elem_context = self._build_context_element(elem)
            elem_tokens = self._estimate_tokens(elem_context)
            if current_tokens + elem_tokens > token_budget:
                break
            context_elements.append(elem_context)
            included_ids.add(elem.id)
            current_tokens += elem_tokens

        # Add relational elements within remaining budget
        # Sort relational elements: verified first, then by name for stability
        relational_sorted = sorted(
            relational_elements, key=lambda e: (not e.verified, e.name)
        )
        relational_context_elements: list[QueryContextElement] = []

        for elem in relational_sorted:
            elem_context = self._build_context_element(elem)
            elem_tokens = self._estimate_tokens(elem_context)
            if current_tokens + elem_tokens > token_budget:
                break
            relational_context_elements.append(elem_context)
            included_ids.add(elem.id)
            current_tokens += elem_tokens

        # Combine all context elements (direct first, then relational)
        all_context_elements = context_elements + relational_context_elements

        # Build relations for included elements
        relations = self._build_relations(direct_elements, included_ids)
        relations_tokens = sum(self._estimate_relation_tokens(r) for r in relations)

        # If relations exceed remaining budget, trim relations
        if current_tokens + relations_tokens > token_budget:
            trimmed_relations: list[QueryContextRelation] = []
            for relation in relations:
                rel_tokens = self._estimate_relation_tokens(relation)
                if current_tokens + rel_tokens > token_budget:
                    break
                trimmed_relations.append(relation)
                current_tokens += rel_tokens
            relations = trimmed_relations
        else:
            current_tokens += relations_tokens

        # Check for unverified elements
        has_unverified = any(not e.verified for e in all_context_elements)

        return QueryContext(
            elements=all_context_elements,
            relations=relations,
            total_tokens=current_tokens,
            has_unverified_elements=has_unverified,
        )

    def _build_context_element(self, elem) -> QueryContextElement:
        """Convert a KnowledgeElement to a QueryContextElement.

        Annotates unverified elements with [UNVERIFIED] marker in content.
        """
        content = elem.content
        if not elem.verified:
            content = f"[UNVERIFIED] {content}"

        return QueryContextElement(
            element_id=elem.id,
            type=elem.type,
            name=elem.name,
            content=content,
            evidence=elem.source_ref.evidence,
            verified=elem.verified,
        )

    def _build_relations(
        self, direct_elements: list[tuple], included_ids: set[str]
    ) -> list[QueryContextRelation]:
        """Build relation entries for elements included in the context.

        Only includes relations where both source and target are in the
        included set.
        """
        relations: list[QueryContextRelation] = []
        seen: set[tuple[str, str, str]] = set()

        for elem, _ in direct_elements:
            if elem.id not in included_ids:
                continue
            for relation in elem.relations:
                if relation.target_id in included_ids:
                    key = (elem.id, relation.target_id, relation.type)
                    if key not in seen:
                        seen.add(key)
                        relations.append(
                            QueryContextRelation(
                                source_id=elem.id,
                                target_id=relation.target_id,
                                type=relation.type,
                                description=relation.description,
                            )
                        )

        return relations

    def _estimate_tokens(self, element: QueryContextElement) -> int:
        """Estimate token count for a context element using len(text) / 4 heuristic."""
        text = f"{element.element_id} {element.type} {element.name} {element.content} {element.evidence}"
        return max(1, len(text) // 4)

    def _estimate_relation_tokens(self, relation: QueryContextRelation) -> int:
        """Estimate token count for a relation entry using len(text) / 4 heuristic."""
        text = f"{relation.source_id} {relation.target_id} {relation.type} {relation.description or ''}"
        return max(1, len(text) // 4)
