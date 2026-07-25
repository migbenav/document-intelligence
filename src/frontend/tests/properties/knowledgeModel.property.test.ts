import { describe, it, expect, vi, beforeEach } from 'vitest';
import fc from 'fast-check';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import type {
  KnowledgeModelResponse,
  KnowledgeElementResponse,
  KnowledgeElementType,
} from '@/types/knowledgeModel';

// Mock the API module
vi.mock('@/api/knowledgeModel', () => ({
  getKnowledgeModel: vi.fn(),
  KnowledgeModelApiError: class KnowledgeModelApiError extends Error {
    status: number;
    code: string;
    constructor(status: number, message: string) {
      super(message);
      this.name = 'KnowledgeModelApiError';
      this.status = status;
      if (status === 404) this.code = 'not_found';
      else if (status === 409) this.code = 'not_ready';
      else this.code = 'unknown';
    }
  },
  KnowledgeModelNetworkError: class KnowledgeModelNetworkError extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.name = 'KnowledgeModelNetworkError';
      this.code = code;
    }
  },
}));

import { getKnowledgeModel } from '@/api/knowledgeModel';

const mockGetKnowledgeModel = vi.mocked(getKnowledgeModel);

// --- Arbitraries ---

const elementTypeArb: fc.Arbitrary<KnowledgeElementType> = fc.constantFrom(
  'proposito',
  'concepto',
  'actor',
  'regla',
  'proceso',
  'restriccion',
);

const relationTypeArb = fc.constantFrom(
  'constrains' as const,
  'participates_in' as const,
  'depends_on' as const,
  'contradicts' as const,
);

const sourceRefArb = (documentId: string) =>
  fc.record({
    document_id: fc.constant(documentId),
    chunk_id: fc.uuid(),
    page: fc.option(fc.integer({ min: 1, max: 500 }), { nil: null }),
    section: fc.option(fc.string({ minLength: 1, maxLength: 50 }), { nil: null }),
    evidence: fc.string({ minLength: 1, maxLength: 200 }),
  });

const relationArb = fc.record({
  target_id: fc.uuid(),
  type: relationTypeArb,
  description: fc.option(fc.string({ minLength: 1, maxLength: 100 }), { nil: null }),
});

const elementArb = (documentId: string): fc.Arbitrary<KnowledgeElementResponse> =>
  fc.record({
    id: fc.uuid(),
    type: elementTypeArb,
    name: fc.string({ minLength: 1, maxLength: 100 }),
    content: fc.string({ minLength: 1, maxLength: 500 }),
    source_ref: sourceRefArb(documentId),
    relations: fc.array(relationArb, { minLength: 0, maxLength: 5 }),
    verified: fc.boolean(),
  });

const knowledgeModelResponseArb = (
  documentId?: string,
): fc.Arbitrary<KnowledgeModelResponse> =>
  (documentId ? fc.constant(documentId) : fc.uuid()).chain((docId) =>
    fc.record({
      document_id: fc.constant(docId),
      document_type: fc.constantFrom('legal_contract', 'technical_spec', 'policy_doc'),
      elements: fc.array(elementArb(docId), { minLength: 1, maxLength: 20 }),
      extraction_metadata: fc.record({
        prompt_version: fc.constant('v1'),
        model_id: fc.constantFrom('gpt-4', 'gpt-4o', 'claude-3'),
        temperature: fc.double({ min: 0, max: 1, noNaN: true }),
        element_count: fc.integer({ min: 1, max: 20 }),
        relationship_count: fc.integer({ min: 0, max: 50 }),
        verification_rate: fc.double({ min: 0, max: 1, noNaN: true }),
        extracted_at: fc.constant('2024-01-01T00:00:00Z'),
      }),
    }),
  );

// --- Tests ---

describe('Knowledge Model Property-Based Tests', () => {
  beforeEach(() => {
    useKnowledgeModelStore.getState().reset();
    vi.clearAllMocks();
  });

  /**
   * Property 1: Data Integrity
   * For any generated KnowledgeModelResponse, the store's loaded state contains
   * exactly the same elements (by id, type, name) as the input response.
   *
   * **Validates: Requirements 1.3, 2.1**
   */
  describe('Property 1: Data Integrity', () => {
    it('store loaded state contains exactly the same elements as the API response', async () => {
      await fc.assert(
        fc.asyncProperty(knowledgeModelResponseArb(), async (response) => {
          // Reset store before each iteration
          useKnowledgeModelStore.getState().reset();

          // Mock API to return the generated response
          mockGetKnowledgeModel.mockResolvedValue(response);

          // Fetch into the store
          await useKnowledgeModelStore
            .getState()
            .fetchKnowledgeModel(response.document_id);

          const state = useKnowledgeModelStore.getState();

          // Store should be in loaded state (elements.length >= 1 from our arb)
          expect(state.status).toBe('loaded');
          expect(state.knowledgeModel).not.toBeNull();

          // Verify exact same number of elements
          expect(state.knowledgeModel!.elements.length).toBe(response.elements.length);

          // Verify each element matches by id, type, and name
          for (const inputElement of response.elements) {
            const storeElement = state.knowledgeModel!.elements.find(
              (e) => e.id === inputElement.id,
            );
            expect(storeElement).toBeDefined();
            expect(storeElement!.type).toBe(inputElement.type);
            expect(storeElement!.name).toBe(inputElement.name);
          }
        }),
        { numRuns: 100 },
      );
    });
  });

  /**
   * Property 4: Cache Validity
   * For any state where knowledgeModel is not null, documentId in store equals
   * knowledgeModel.document_id.
   *
   * **Validates: Requirements 1.6**
   */
  describe('Property 4: Cache Validity', () => {
    it('documentId in store always equals knowledgeModel.document_id when loaded', async () => {
      await fc.assert(
        fc.asyncProperty(fc.uuid(), async (documentId) => {
          // Reset store before each iteration
          useKnowledgeModelStore.getState().reset();

          // Generate a response with matching document_id
          const response: KnowledgeModelResponse = {
            document_id: documentId,
            document_type: 'legal_contract',
            elements: [
              {
                id: 'elem-1',
                type: 'concepto',
                name: 'Test Element',
                content: 'Test content',
                source_ref: {
                  document_id: documentId,
                  chunk_id: 'chunk-1',
                  page: 1,
                  section: 'Section 1',
                  evidence: 'Evidence text',
                },
                relations: [],
                verified: true,
              },
            ],
            extraction_metadata: {
              prompt_version: 'v1',
              model_id: 'gpt-4',
              temperature: 0.2,
              element_count: 1,
              relationship_count: 0,
              verification_rate: 1.0,
              extracted_at: '2024-01-01T00:00:00Z',
            },
          };

          mockGetKnowledgeModel.mockResolvedValue(response);

          // Fetch with the generated documentId
          await useKnowledgeModelStore.getState().fetchKnowledgeModel(documentId);

          const state = useKnowledgeModelStore.getState();

          // When knowledgeModel is not null, documentId must match
          if (state.knowledgeModel !== null) {
            expect(state.documentId).toBe(state.knowledgeModel.document_id);
          }
        }),
        { numRuns: 100 },
      );
    });
  });

  /**
   * Property 7: Navigation History Integrity
   * For any sequence of navigateToElement calls followed by goBack calls,
   * selectedElementId returns to each previously selected element in LIFO order,
   * and history never contains the currently selected element.
   *
   * **Validates: Requirements 3.8, 6.3**
   */
  describe('Property 7: Navigation History Integrity', () => {
    it('goBack returns through history in LIFO order and history never contains current selection', () => {
      fc.assert(
        fc.property(
          // Generate a sequence of unique element IDs (at least 2 for meaningful navigation)
          fc.array(fc.uuid(), { minLength: 2, maxLength: 20 }).filter((ids) => {
            // Ensure all IDs are unique
            return new Set(ids).size === ids.length;
          }),
          (elementIds) => {
            // Reset store
            useKnowledgeModelStore.getState().reset();

            // Select the first element (this clears history)
            const [firstId, ...restIds] = elementIds;
            useKnowledgeModelStore.getState().selectElement(firstId!);

            // Navigate to subsequent elements (builds history)
            for (const id of restIds) {
              useKnowledgeModelStore.getState().navigateToElement(id);

              // INVARIANT: history never contains the currently selected element
              const currentState = useKnowledgeModelStore.getState();
              expect(currentState.navigationHistory).not.toContain(
                currentState.selectedElementId,
              );
            }

            // Now go back through the entire history and verify LIFO order
            // Expected order when going back: restIds in reverse (excluding last which is current),
            // then firstId
            const expectedBackOrder = [firstId, ...restIds.slice(0, -1)].reverse();

            for (const expectedId of expectedBackOrder) {
              useKnowledgeModelStore.getState().goBack();
              const state = useKnowledgeModelStore.getState();

              expect(state.selectedElementId).toBe(expectedId);

              // INVARIANT: history never contains the currently selected element
              expect(state.navigationHistory).not.toContain(state.selectedElementId);
            }

            // One more goBack should deselect (null)
            useKnowledgeModelStore.getState().goBack();
            expect(useKnowledgeModelStore.getState().selectedElementId).toBeNull();
            expect(useKnowledgeModelStore.getState().navigationHistory).toEqual([]);
          },
        ),
        { numRuns: 100 },
      );
    });
  });
});
