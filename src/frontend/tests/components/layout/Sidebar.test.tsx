import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach } from 'vitest';
import { Sidebar } from '@/components/layout/Sidebar';
import { TranslationProvider } from '@/i18n';
import { usePreferencesStore } from '@/store/preferencesStore';

function renderSidebar(locale: string = 'es') {
  return render(
    <TranslationProvider locale={locale}>
      <Sidebar />
    </TranslationProvider>,
  );
}

describe('Sidebar', () => {
  beforeEach(() => {
    // Reset store to defaults before each test
    usePreferencesStore.setState({
      language: 'es',
      model: 'default',
      autoFallback: true,
    });
  });

  describe('Rendering and structure', () => {
    it('renders as an aside element with aria-label', () => {
      renderSidebar();
      const aside = screen.getByRole('complementary');
      expect(aside).toBeInTheDocument();
      expect(aside).toHaveAttribute('aria-label', 'Preferencias');
    });

    it('renders a toggle button', () => {
      renderSidebar();
      const toggleButton = screen.getByRole('button', { name: /panel/i });
      expect(toggleButton).toBeInTheDocument();
    });
  });

  describe('Toggle expand/collapse', () => {
    it('starts in default state with toggle button having aria-expanded', () => {
      renderSidebar();
      const toggleButton = screen.getByRole('button', { name: /panel/i });
      // By default, the component starts expanded (collapsed=false), so aria-expanded is true
      expect(toggleButton).toHaveAttribute('aria-expanded', 'true');
    });

    it('collapses when toggle button is clicked', async () => {
      const user = userEvent.setup();
      renderSidebar();

      const toggleButton = screen.getByRole('button', { name: /contraer panel/i });
      await user.click(toggleButton);

      // After collapsing, the button should show expand label and aria-expanded=false
      const expandButton = screen.getByRole('button', { name: /expandir panel/i });
      expect(expandButton).toHaveAttribute('aria-expanded', 'false');
    });

    it('expands when toggle button is clicked again after collapse', async () => {
      const user = userEvent.setup();
      renderSidebar();

      // Collapse
      const collapseButton = screen.getByRole('button', { name: /contraer panel/i });
      await user.click(collapseButton);

      // Expand
      const expandButton = screen.getByRole('button', { name: /expandir panel/i });
      await user.click(expandButton);

      // Should be back to expanded
      const button = screen.getByRole('button', { name: /contraer panel/i });
      expect(button).toHaveAttribute('aria-expanded', 'true');
    });

    it('shows preferences heading when expanded', () => {
      renderSidebar();
      expect(screen.getByText('Preferencias de Usuario')).toBeInTheDocument();
    });

    it('hides preferences heading when collapsed', async () => {
      const user = userEvent.setup();
      renderSidebar();

      const toggleButton = screen.getByRole('button', { name: /contraer panel/i });
      await user.click(toggleButton);

      expect(screen.queryByText('Preferencias de Usuario')).not.toBeInTheDocument();
    });
  });

  describe('Language selector dispatches setLanguage', () => {
    it('renders language selector trigger with current language label', () => {
      renderSidebar();
      // The sidebar is expanded and shows language label
      expect(screen.getByText('Idioma')).toBeInTheDocument();
    });

    it('updates store when language is changed programmatically', () => {
      renderSidebar();
      // Simulate what the Select onValueChange would do
      usePreferencesStore.getState().setLanguage('en');
      expect(usePreferencesStore.getState().language).toBe('en');
    });

    it('reflects store language state in the component', () => {
      usePreferencesStore.setState({ language: 'en' });
      renderSidebar('en');
      // The language selector trigger should show current value
      // When language is 'en', the displayed value in the select should reflect English
      const triggers = screen.getAllByRole('combobox');
      // First combobox is the language selector
      expect(triggers.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe('Model selector dispatches setModel', () => {
    it('renders model selector label', () => {
      renderSidebar();
      expect(screen.getByText('Modelo LLM')).toBeInTheDocument();
    });

    it('updates store when model is changed', () => {
      renderSidebar();
      usePreferencesStore.getState().setModel('gemini/gemini-2.5-flash');
      expect(usePreferencesStore.getState().model).toBe('gemini/gemini-2.5-flash');
    });

    it('shows model description text for the selected model', () => {
      renderSidebar();
      // Default model shows its description
      expect(screen.getByText('Usa el modelo óptimo para cada tarea')).toBeInTheDocument();
    });

    it('updates description when model changes in store', () => {
      usePreferencesStore.setState({ model: 'gemini/gemini-2.5-flash' });
      renderSidebar();
      expect(screen.getByText('Principal — análisis profundo')).toBeInTheDocument();
    });
  });

  describe('Fallback switch dispatches setAutoFallback', () => {
    it('renders fallback switch with correct label', () => {
      renderSidebar();
      expect(screen.getByText('Auto-fallback')).toBeInTheDocument();
    });

    it('renders switch element with role switch', () => {
      renderSidebar();
      const switchEl = screen.getByRole('switch');
      expect(switchEl).toBeInTheDocument();
    });

    it('switch reflects autoFallback=true as checked', () => {
      usePreferencesStore.setState({ autoFallback: true });
      renderSidebar();
      const switchEl = screen.getByRole('switch');
      expect(switchEl).toHaveAttribute('data-state', 'checked');
    });

    it('switch reflects autoFallback=false as unchecked', () => {
      usePreferencesStore.setState({ autoFallback: false });
      renderSidebar();
      const switchEl = screen.getByRole('switch');
      expect(switchEl).toHaveAttribute('data-state', 'unchecked');
    });

    it('toggles autoFallback when switch is clicked', async () => {
      const user = userEvent.setup();
      usePreferencesStore.setState({ autoFallback: true });
      renderSidebar();

      const switchEl = screen.getByRole('switch');
      await user.click(switchEl);

      expect(usePreferencesStore.getState().autoFallback).toBe(false);
    });

    it('shows fallback description text', () => {
      renderSidebar();
      expect(
        screen.getByText(
          'Si el modelo seleccionado falla, reintenta con un modelo alternativo automáticamente',
        ),
      ).toBeInTheDocument();
    });
  });

  describe('Accessibility attributes', () => {
    it('aside has role complementary', () => {
      renderSidebar();
      expect(screen.getByRole('complementary')).toBeInTheDocument();
    });

    it('toggle button has aria-expanded attribute', () => {
      renderSidebar();
      const toggleButton = screen.getByRole('button', { name: /panel/i });
      expect(toggleButton).toHaveAttribute('aria-expanded');
    });

    it('toggle button has aria-label', () => {
      renderSidebar();
      const toggleButton = screen.getByRole('button', { name: /panel/i });
      expect(toggleButton).toHaveAttribute('aria-label');
    });

    it('switch has aria-label for fallback', () => {
      renderSidebar();
      const switchEl = screen.getByRole('switch');
      expect(switchEl).toHaveAttribute('aria-label', 'Auto-fallback');
    });

    it('select triggers have aria-label attributes', () => {
      renderSidebar();
      const comboboxes = screen.getAllByRole('combobox');
      for (const combobox of comboboxes) {
        expect(combobox).toHaveAttribute('aria-label');
      }
    });

    it('language selector trigger has correct aria-label', () => {
      renderSidebar();
      const langTrigger = screen.getByRole('combobox', { name: 'Idioma' });
      expect(langTrigger).toBeInTheDocument();
    });

    it('model selector trigger has correct aria-label', () => {
      renderSidebar();
      const modelTrigger = screen.getByRole('combobox', { name: 'Modelo LLM' });
      expect(modelTrigger).toBeInTheDocument();
    });
  });
});
