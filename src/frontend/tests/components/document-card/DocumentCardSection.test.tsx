import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { TranslationProvider } from '@/i18n';
import { CardApiError } from '@/api/documentCard';
import type { DocumentCard } from '@/types/documentCard';

// We need to mock fetchCard at the API level since the component calls it directly
const mockFetchCardApi = vi.fn();
const mockRetryLlmApi = vi.fn();

vi.mock('@/api/documentCard', () => ({
  fetchCard: (...args: unknown[]) => mockFetchCardApi(...args),
  retryLlm: (...args: unknown[]) => mockRetryLlmApi(...args),
  CardApiError: class CardApiError extends Error {
    status: number;
    code: string;
    constructor(status: number, code: string, message: string) {
      super(message);
      this.name = 'CardApiError';
      this.status = status;
      this.code = code;
    }
  },
}));

// Mock the store to return controlled values
const mockStoreRetryLlm = vi.fn();
const mockStoreReset = vi.fn();
let mockStoreCard: DocumentCard | null = null;

vi.mock('@/store/documentCardStore', () => ({
  useDocumentCardStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      card: mockStoreCard,
      loading: false,
      error: null,
      fetchCard: vi.fn(),
      retryLlm: mockStoreRetryLlm,
      reset: mockStoreReset,
    }),
}));

// Import the component AFTER mocks are set up
import { DocumentCardSection } from '@/components/document-card/DocumentCardSection';

const completedCard: DocumentCard = {
  id: 'card-1',
  document_id: 'doc-1',
  title: 'Reglamento de Propiedad Horizontal',
  summary: 'Summary of the document.',
  classification: 'normative',
  organization_type: 'numbered_articles',
  statistics: {
    total_chunks: 45,
    sections_detected: 12,
    hierarchy_levels: 3,
    has_existing_index: true,
  },
  file_metadata: {
    size_bytes: 234500,
    format: 'pdf',
    language: 'es',
    last_modified: null,
  },
  status: 'completed',
  outdated: false,
  model_id: 'groq/llama-3.3-70b-versatile',
  prompt_version: 'base-analysis-v1',
  created_at: '2026-07-26T10:30:00Z',
  updated_at: '2026-07-26T10:30:04Z',
};

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <TranslationProvider locale="en">{ui}</TranslationProvider>,
  );
}

describe('DocumentCardSection', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    mockStoreCard = null;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows skeleton on initial render while polling', async () => {
    mockFetchCardApi.mockRejectedValue(
      new CardApiError(404, 'card_not_found', 'Card not found'),
    );

    await act(async () => {
      renderWithProviders(<DocumentCardSection documentId="doc-1" />);
    });

    expect(screen.getByTestId('document-card-skeleton')).toBeInTheDocument();
  });

  it('shows DocumentCardView when card is fetched on first poll', async () => {
    mockFetchCardApi.mockResolvedValue(completedCard);

    await act(async () => {
      renderWithProviders(<DocumentCardSection documentId="doc-1" />);
    });

    // Wait for the first async poll to resolve
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(screen.getByTestId('document-card-view')).toBeInTheDocument();
  });

  it('shows card after subsequent poll succeeds', async () => {
    mockFetchCardApi
      .mockRejectedValueOnce(new CardApiError(404, 'card_not_found', 'Card not found'))
      .mockResolvedValueOnce(completedCard);

    await act(async () => {
      renderWithProviders(<DocumentCardSection documentId="doc-1" />);
    });

    // First poll (immediate) returns 404
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByTestId('document-card-skeleton')).toBeInTheDocument();

    // Second poll at 1.5s returns card
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });

    expect(screen.getByTestId('document-card-view')).toBeInTheDocument();
  });

  it('shows poll exhausted message after 10 failed attempts', async () => {
    mockFetchCardApi.mockRejectedValue(
      new CardApiError(404, 'card_not_found', 'Card not found'),
    );

    await act(async () => {
      renderWithProviders(<DocumentCardSection documentId="doc-1" />);
    });

    // Advance through all polls: 1 immediate + 9 intervals
    for (let i = 0; i < 10; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500);
      });
    }

    expect(screen.getByTestId('document-card-poll-exhausted')).toBeInTheDocument();
    expect(screen.getByTestId('card-manual-retry-button')).toBeInTheDocument();
  });

  it('manual retry button restarts polling and shows card on success', async () => {
    mockFetchCardApi.mockRejectedValue(
      new CardApiError(404, 'card_not_found', 'Card not found'),
    );

    await act(async () => {
      renderWithProviders(<DocumentCardSection documentId="doc-1" />);
    });

    // Exhaust polling
    for (let i = 0; i < 10; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500);
      });
    }

    expect(screen.getByTestId('document-card-poll-exhausted')).toBeInTheDocument();

    // Now configure success for the next fetch
    mockFetchCardApi.mockResolvedValue(completedCard);

    // Click manual retry using fireEvent (avoids fake timers conflict with userEvent)
    const button = screen.getByTestId('card-manual-retry-button');
    await act(async () => {
      button.click();
    });

    // The first immediate poll in the new cycle should succeed
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(screen.getByTestId('document-card-view')).toBeInTheDocument();
  });
});
