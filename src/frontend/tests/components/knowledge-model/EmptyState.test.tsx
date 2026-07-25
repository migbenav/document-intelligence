import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { EmptyState } from '@/components/knowledge-model/EmptyState';
import { TranslationProvider } from '@/i18n';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

describe('EmptyState', () => {
  it('renders the empty state message', () => {
    renderWithProviders(<EmptyState />);

    expect(
      screen.getByText('No knowledge elements were extracted from this document.'),
    ).toBeInTheDocument();
  });

  it('renders with the test id', () => {
    renderWithProviders(<EmptyState />);

    expect(screen.getByTestId('km-empty-state')).toBeInTheDocument();
  });
});
