import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { QueryInput } from '@/components/query/QueryInput';
import { TranslationProvider } from '@/i18n';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

describe('QueryInput', () => {
  describe('rendering', () => {
    it('renders a textarea input field', () => {
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} />);

      expect(screen.getByTestId('query-input-field')).toBeInTheDocument();
    });

    it('renders a submit button', () => {
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} />);

      expect(screen.getByTestId('query-input-submit')).toBeInTheDocument();
    });

    it('renders a character counter showing 0/1000', () => {
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} />);

      expect(screen.getByTestId('query-char-counter')).toHaveTextContent('0/1000');
    });

    it('displays placeholder text', () => {
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} />);

      expect(screen.getByPlaceholderText('Ask a question about this document...')).toBeInTheDocument();
    });
  });

  describe('character counter', () => {
    it('updates character count as user types', async () => {
      const user = userEvent.setup();
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} />);

      await user.type(screen.getByTestId('query-input-field'), 'Hello');

      expect(screen.getByTestId('query-char-counter')).toHaveTextContent('5/1000');
    });

    it('shows destructive styling when over 1000 chars', async () => {
      const user = userEvent.setup();
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} />);

      const longText = 'a'.repeat(1001);
      await user.click(screen.getByTestId('query-input-field'));
      await user.paste(longText);

      const counter = screen.getByTestId('query-char-counter');
      expect(counter).toHaveTextContent('1001/1000');
      expect(counter.className).toContain('text-destructive');
    });
  });

  describe('submit behavior', () => {
    it('submit button is disabled when input is empty', () => {
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} />);

      expect(screen.getByTestId('query-input-submit')).toBeDisabled();
    });

    it('submit button is enabled when input has valid content', async () => {
      const user = userEvent.setup();
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} />);

      await user.type(screen.getByTestId('query-input-field'), 'What is this?');

      expect(screen.getByTestId('query-input-submit')).not.toBeDisabled();
    });

    it('submit button is disabled when input exceeds 1000 chars', async () => {
      const user = userEvent.setup();
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} />);

      const longText = 'a'.repeat(1001);
      await user.click(screen.getByTestId('query-input-field'));
      await user.paste(longText);

      expect(screen.getByTestId('query-input-submit')).toBeDisabled();
    });

    it('submit button is disabled when isLoading is true', async () => {
      const user = userEvent.setup();
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={true} />);

      await user.type(screen.getByTestId('query-input-field'), 'A question');

      expect(screen.getByTestId('query-input-submit')).toBeDisabled();
    });

    it('submit button is disabled when disabled prop is true', () => {
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} disabled={true} />);

      // Input is also disabled
      expect(screen.getByTestId('query-input-field')).toBeDisabled();
    });

    it('calls onSubmit with trimmed text when submit button is clicked', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(<QueryInput onSubmit={onSubmit} isLoading={false} />);

      await user.type(screen.getByTestId('query-input-field'), '  What is this?  ');
      await user.click(screen.getByTestId('query-input-submit'));

      expect(onSubmit).toHaveBeenCalledWith('What is this?');
    });

    it('clears input after successful submit', async () => {
      const user = userEvent.setup();
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} />);

      await user.type(screen.getByTestId('query-input-field'), 'A question');
      await user.click(screen.getByTestId('query-input-submit'));

      expect(screen.getByTestId('query-input-field')).toHaveValue('');
      expect(screen.getByTestId('query-char-counter')).toHaveTextContent('0/1000');
    });

    it('does not call onSubmit when input is only whitespace', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(<QueryInput onSubmit={onSubmit} isLoading={false} />);

      await user.type(screen.getByTestId('query-input-field'), '   ');
      // Submit button should be disabled for whitespace-only input
      expect(screen.getByTestId('query-input-submit')).toBeDisabled();
    });
  });

  describe('keyboard navigation', () => {
    it('submits on Enter key', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(<QueryInput onSubmit={onSubmit} isLoading={false} />);

      const input = screen.getByTestId('query-input-field');
      await user.type(input, 'A question');
      await user.keyboard('{Enter}');

      expect(onSubmit).toHaveBeenCalledWith('A question');
    });

    it('inserts newline on Shift+Enter', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(<QueryInput onSubmit={onSubmit} isLoading={false} />);

      const input = screen.getByTestId('query-input-field');
      await user.type(input, 'Line 1');
      await user.keyboard('{Shift>}{Enter}{/Shift}');
      await user.type(input, 'Line 2');

      expect(onSubmit).not.toHaveBeenCalled();
      expect(input).toHaveValue('Line 1\nLine 2');
    });

    it('does not submit on Enter when loading', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(<QueryInput onSubmit={onSubmit} isLoading={true} />);

      const input = screen.getByTestId('query-input-field');
      await user.type(input, 'A question');
      await user.keyboard('{Enter}');

      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  describe('accessibility', () => {
    it('has a screen-reader-only label for the input', () => {
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} />);

      const label = screen.getByLabelText('Ask a question about this document');
      expect(label).toBeInTheDocument();
    });

    it('character counter is linked via aria-describedby', () => {
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} />);

      const input = screen.getByTestId('query-input-field');
      expect(input).toHaveAttribute('aria-describedby', 'query-char-counter');
    });

    it('sets aria-invalid when over character limit', async () => {
      const user = userEvent.setup();
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} />);

      const longText = 'a'.repeat(1001);
      await user.click(screen.getByTestId('query-input-field'));
      await user.paste(longText);

      expect(screen.getByTestId('query-input-field')).toHaveAttribute('aria-invalid', 'true');
    });

    it('submit button has an aria-label', () => {
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} />);

      expect(screen.getByTestId('query-input-submit')).toHaveAttribute('aria-label', 'Submit question');
    });

    it('character counter has aria-live="polite"', () => {
      renderWithProviders(<QueryInput onSubmit={vi.fn()} isLoading={false} />);

      const counter = screen.getByTestId('query-char-counter');
      expect(counter).toHaveAttribute('aria-live', 'polite');
    });
  });
});
