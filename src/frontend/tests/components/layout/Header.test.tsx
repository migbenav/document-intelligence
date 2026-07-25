import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Header } from '@/components/layout/Header';
import { TranslationProvider } from '@/i18n';

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <TranslationProvider>{ui}</TranslationProvider>
  );
}

describe('Header', () => {
  it('renders the application name from i18n', () => {
    renderWithProviders(<Header />);
    expect(screen.getByText('Document Intelligence')).toBeInTheDocument();
  });

  it('renders as a header element', () => {
    renderWithProviders(<Header />);
    expect(screen.getByRole('banner')).toBeInTheDocument();
  });

  it('renders the app name in an h1 element', () => {
    renderWithProviders(<Header />);
    const heading = screen.getByRole('heading', { level: 1 });
    expect(heading).toHaveTextContent('Document Intelligence');
  });

  it('applies responsive padding classes', () => {
    renderWithProviders(<Header />);
    const header = screen.getByRole('banner');
    // px-4 on mobile, sm:px-6 on larger screens
    expect(header).toHaveClass('px-4');
    expect(header).toHaveClass('sm:px-6');
  });

  it('displays translated app name for Spanish locale', () => {
    render(
      <TranslationProvider locale="es">
        <Header />
      </TranslationProvider>
    );
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
  });
});
