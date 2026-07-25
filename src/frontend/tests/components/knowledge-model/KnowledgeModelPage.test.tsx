import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { KnowledgeModelPage } from '@/components/knowledge-model/KnowledgeModelPage';
import { TranslationProvider } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import type { KnowledgeModelResponse } from '@/types/knowledgeModel';

vi.mock('@/api/knowledgeModel', () => ({
  getKnowledgeModel: vi.fn(),
  KnowledgeModelApiError: class extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.code = code;
    }
  },
  KnowledgeModelNetworkError: class extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.code = code;
    }
  },
}));

// Mock window.matchMedia for ElementDetailPanel's useIsMobile hook
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

/** Helper to set store state with a no-op fetchKnowledgeModel to avoid useEffect overriding state */
function setStoreWithNoopFetch(state: Record<string, unknown>) {
  useKnowledgeModelStore.setState({
    fetchKnowledgeModel: vi.fn(),
    ...state,
  });
}

const mockKnowledgeModel: KnowledgeModelResponse = {
  document_id: 'doc-1',
  document_type: 'requirements',
  elements: [
    {
      id: 'el-1',
      type: 'concepto',
      name: 'Test Concept',
      content: 'This is a test concept description.',
      source_ref: {
        document_id: 'doc-1',
        chunk_id: 'chunk-1',
        page: null,
        section: 'Introduction',
        evidence: 'test evidence text',
      },
      relations: [],
      verified: true,
    },
    {
      id: 'el-2',
      type: 'actor',
      name: 'Test Actor',
      content: 'This is a test actor.',
      source_ref: {
        document_id: 'doc-1',
        chunk_id: 'chunk-2',
        page: 1,
        section: null,
        evidence: 'actor evidence',
      },
      relations: [
        { target_id: 'el-1', type: 'depends_on', description: null },
      ],
      verified: false,
    },
  ],
  extraction_metadata: {
    prompt_version: 'v1',
    model_id: 'gpt-4',
    temperature: 0.2,
    element_count: 2,
    relationship_count: 1,
    verification_rate: 0.5,
    extracted_at: '2024-01-01T00:00:00Z',
  },
};

describe('KnowledgeModelPage', () => {
  beforeEach(() => {
    useKnowledgeModelStore.getState().reset();
  });

  it('renders loading state when status is idle', () => {
    setStoreWithNoopFetch({ status: 'idle' });

    renderWithProviders(<KnowledgeModelPage documentId="doc-1" />);

    expect(screen.getByTestId('km-loading-state')).toBeInTheDocument();
  });

  it('renders loading state when status is loading', () => {
    setStoreWithNoopFetch({ status: 'loading' });

    renderWithProviders(<KnowledgeModelPage documentId="doc-1" />);

    expect(screen.getByTestId('km-loading-state')).toBeInTheDocument();
  });

  it('renders empty state when status is empty', () => {
    setStoreWithNoopFetch({ status: 'empty' });

    renderWithProviders(<KnowledgeModelPage documentId="doc-1" />);

    expect(screen.getByTestId('km-empty-state')).toBeInTheDocument();
  });

  it('renders error state when status is error', () => {
    setStoreWithNoopFetch({
      status: 'error',
      error: 'Something went wrong',
    });

    renderWithProviders(<KnowledgeModelPage documentId="doc-1" />);

    expect(screen.getByTestId('km-error-state')).toBeInTheDocument();
    expect(screen.getByTestId('km-error-message')).toHaveTextContent('Something went wrong');
  });

  it('renders KMHeader and ElementListView when loaded in list mode', () => {
    setStoreWithNoopFetch({
      status: 'loaded',
      knowledgeModel: mockKnowledgeModel,
      viewMode: 'list',
      documentId: 'doc-1',
    });

    renderWithProviders(<KnowledgeModelPage documentId="doc-1" />);

    expect(screen.getByTestId('km-header')).toBeInTheDocument();
    expect(screen.getByTestId('element-list-view')).toBeInTheDocument();
  });

  it('renders graph placeholder when loaded in graph mode', () => {
    setStoreWithNoopFetch({
      status: 'loaded',
      knowledgeModel: mockKnowledgeModel,
      viewMode: 'graph',
      documentId: 'doc-1',
    });

    renderWithProviders(<KnowledgeModelPage documentId="doc-1" />);

    expect(screen.getByTestId('km-graph-placeholder')).toBeInTheDocument();
    expect(screen.getByText('Graph view coming soon')).toBeInTheDocument();
  });

  it('renders ElementDetailPanel when an element is selected', () => {
    setStoreWithNoopFetch({
      status: 'loaded',
      knowledgeModel: mockKnowledgeModel,
      viewMode: 'list',
      selectedElementId: 'el-1',
      documentId: 'doc-1',
    });

    renderWithProviders(<KnowledgeModelPage documentId="doc-1" />);

    expect(screen.getByTestId('element-detail-panel')).toBeInTheDocument();
    expect(screen.getByTestId('detail-panel-heading')).toHaveTextContent('Test Concept');
  });

  it('does not render ElementDetailPanel when no element is selected', () => {
    setStoreWithNoopFetch({
      status: 'loaded',
      knowledgeModel: mockKnowledgeModel,
      viewMode: 'list',
      selectedElementId: null,
      documentId: 'doc-1',
    });

    renderWithProviders(<KnowledgeModelPage documentId="doc-1" />);

    expect(screen.queryByTestId('element-detail-panel')).not.toBeInTheDocument();
  });

  it('does not render detail panel when selectedElementId does not match any element', () => {
    setStoreWithNoopFetch({
      status: 'loaded',
      knowledgeModel: mockKnowledgeModel,
      viewMode: 'list',
      selectedElementId: 'nonexistent-id',
      documentId: 'doc-1',
    });

    renderWithProviders(<KnowledgeModelPage documentId="doc-1" />);

    expect(screen.queryByTestId('element-detail-panel')).not.toBeInTheDocument();
  });

  it('calls fetchKnowledgeModel on mount', async () => {
    const fetchSpy = vi.fn();
    useKnowledgeModelStore.setState({ fetchKnowledgeModel: fetchSpy });

    renderWithProviders(<KnowledgeModelPage documentId="doc-1" />);

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith('doc-1');
    });
  });

  it('has data-testid="km-page" wrapper on all states', () => {
    setStoreWithNoopFetch({ status: 'loading' });
    const { unmount } = renderWithProviders(<KnowledgeModelPage documentId="doc-1" />);
    expect(screen.getByTestId('km-page')).toBeInTheDocument();
    unmount();

    setStoreWithNoopFetch({ status: 'empty' });
    const { unmount: unmount2 } = renderWithProviders(<KnowledgeModelPage documentId="doc-1" />);
    expect(screen.getByTestId('km-page')).toBeInTheDocument();
    unmount2();

    setStoreWithNoopFetch({ status: 'error', error: 'err' });
    const { unmount: unmount3 } = renderWithProviders(<KnowledgeModelPage documentId="doc-1" />);
    expect(screen.getByTestId('km-page')).toBeInTheDocument();
    unmount3();
  });
});
