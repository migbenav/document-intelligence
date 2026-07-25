import { render, screen } from '@testing-library/react';
import { TranslationProvider, useTranslation } from '@/i18n';

function TestConsumer({ translationKey, params }: { translationKey: string; params?: Record<string, string> }) {
  const { t } = useTranslation();
  return <span data-testid="output">{t(translationKey, params)}</span>;
}

function LocaleDisplay() {
  const { locale } = useTranslation();
  return <span data-testid="locale">{locale}</span>;
}

describe('useTranslation', () => {
  describe('nested key lookup', () => {
    it('resolves top-level keys', () => {
      render(
        <TranslationProvider>
          <TestConsumer translationKey="app.name" />
        </TranslationProvider>,
      );
      expect(screen.getByTestId('output')).toHaveTextContent('Document Intelligence');
    });

    it('resolves deeply nested keys', () => {
      render(
        <TranslationProvider>
          <TestConsumer translationKey="consent.details.sent" />
        </TranslationProvider>,
      );
      expect(screen.getByTestId('output')).toHaveTextContent(
        'Only the document text and system prompts are sent.',
      );
    });

    it('resolves keys in different sections', () => {
      render(
        <TranslationProvider>
          <TestConsumer translationKey="actions.retry" />
        </TranslationProvider>,
      );
      expect(screen.getByTestId('output')).toHaveTextContent('Try again');
    });
  });

  describe('missing key fallback', () => {
    it('returns the key itself when not found', () => {
      render(
        <TranslationProvider>
          <TestConsumer translationKey="nonexistent.key" />
        </TranslationProvider>,
      );
      expect(screen.getByTestId('output')).toHaveTextContent('nonexistent.key');
    });

    it('returns the key when path partially matches but ends at object', () => {
      render(
        <TranslationProvider>
          <TestConsumer translationKey="consent.details" />
        </TranslationProvider>,
      );
      expect(screen.getByTestId('output')).toHaveTextContent('consent.details');
    });
  });

  describe('interpolation', () => {
    it('replaces {placeholder} with provided value', () => {
      render(
        <TranslationProvider>
          <TestConsumer translationKey="errors.fileTooLarge" params={{ limit: '10 MB' }} />
        </TranslationProvider>,
      );
      expect(screen.getByTestId('output')).toHaveTextContent(
        'File exceeds the size limit of 10 MB.',
      );
    });

    it('leaves unmatched placeholders intact', () => {
      render(
        <TranslationProvider>
          <TestConsumer translationKey="errors.fileTooLarge" params={{ other: 'value' }} />
        </TranslationProvider>,
      );
      expect(screen.getByTestId('output')).toHaveTextContent(
        'File exceeds the size limit of {limit}.',
      );
    });

    it('handles strings without placeholders gracefully', () => {
      render(
        <TranslationProvider>
          <TestConsumer translationKey="app.name" params={{ limit: '5' }} />
        </TranslationProvider>,
      );
      expect(screen.getByTestId('output')).toHaveTextContent('Document Intelligence');
    });
  });

  describe('locale switching', () => {
    it('defaults to English', () => {
      render(
        <TranslationProvider>
          <LocaleDisplay />
        </TranslationProvider>,
      );
      expect(screen.getByTestId('locale')).toHaveTextContent('en');
    });

    it('loads Spanish translations when locale is es', () => {
      render(
        <TranslationProvider locale="es">
          <TestConsumer translationKey="upload.title" />
        </TranslationProvider>,
      );
      expect(screen.getByTestId('output')).toHaveTextContent('Subir un documento');
    });

    it('falls back to English for unknown locale', () => {
      render(
        <TranslationProvider locale="fr">
          <TestConsumer translationKey="app.name" />
        </TranslationProvider>,
      );
      expect(screen.getByTestId('output')).toHaveTextContent('Document Intelligence');
    });

    it('reports the active locale', () => {
      render(
        <TranslationProvider locale="es">
          <LocaleDisplay />
        </TranslationProvider>,
      );
      expect(screen.getByTestId('locale')).toHaveTextContent('es');
    });
  });

  describe('error handling', () => {
    it('throws when used outside TranslationProvider', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      expect(() => render(<TestConsumer translationKey="app.name" />)).toThrow(
        'useTranslation must be used within a TranslationProvider',
      );
      consoleSpy.mockRestore();
    });
  });
});
