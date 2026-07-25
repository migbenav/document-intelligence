import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { AppShell } from '@/components/layout/AppShell';
import { TranslationProvider } from '@/i18n';

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <TranslationProvider>{ui}</TranslationProvider>
  );
}

describe('AppShell', () => {
  it('renders a flex column layout with min-h-screen', () => {
    const { container } = renderWithProviders(
      <AppShell><p>Content</p></AppShell>
    );
    const shell = container.firstElementChild as HTMLElement;
    expect(shell).toHaveClass('flex', 'min-h-screen', 'flex-col');
  });

  it('renders header and main content area', () => {
    renderWithProviders(
      <AppShell><p>Child content</p></AppShell>
    );
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('main')).toBeInTheDocument();
    expect(screen.getByText('Child content')).toBeInTheDocument();
  });

  it('wraps children in a centered max-w-2xl container', () => {
    renderWithProviders(
      <AppShell><p data-testid="child">Hello</p></AppShell>
    );
    const child = screen.getByTestId('child');
    const container = child.parentElement as HTMLElement;
    expect(container).toHaveClass('w-full', 'max-w-2xl');
  });

  it('applies responsive padding to the main area', () => {
    renderWithProviders(
      <AppShell><p>Content</p></AppShell>
    );
    const main = screen.getByRole('main');
    // px-4 for mobile, md:px-6 for desktop
    expect(main).toHaveClass('px-4');
    expect(main).toHaveClass('md:px-6');
  });
});
