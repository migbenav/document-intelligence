import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import App from '../src/App';
import { TranslationProvider } from '../src/i18n';

function renderApp() {
  return render(
    <TranslationProvider>
      <App />
    </TranslationProvider>
  );
}

describe('App', () => {
  it('renders the application header with app name', () => {
    renderApp();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Document Intelligence');
  });

  it('renders the upload zone', () => {
    renderApp();
    expect(screen.getByText('Drag and drop your file here, or click to browse')).toBeInTheDocument();
  });

  it('uses AppShell layout with header and main', () => {
    renderApp();
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('main')).toBeInTheDocument();
  });
});
