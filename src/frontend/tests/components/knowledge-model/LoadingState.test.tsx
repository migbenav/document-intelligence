import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { LoadingState } from '@/components/knowledge-model/LoadingState';
import { TranslationProvider } from '@/i18n';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

describe('LoadingState', () => {
  it('renders a spinner with the loading message', () => {
    renderWithProviders(<LoadingState />);

    expect(screen.getByText('Loading Knowledge Model...')).toBeInTheDocument();
  });

  it('renders a status element with accessible label', () => {
    renderWithProviders(<LoadingState />);

    const spinner = screen.getByRole('status');
    expect(spinner).toBeInTheDocument();
    expect(spinner).toHaveAttribute('aria-label', 'Loading Knowledge Model...');
  });

  it('renders with the test id', () => {
    renderWithProviders(<LoadingState />);

    expect(screen.getByTestId('km-loading-state')).toBeInTheDocument();
  });
});
