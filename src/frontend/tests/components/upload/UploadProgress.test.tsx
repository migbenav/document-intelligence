import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { UploadProgress } from '@/components/upload/UploadProgress';
import { TranslationProvider } from '@/i18n';
import { useUploadStore } from '@/store/uploadStore';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

describe('UploadProgress', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useUploadStore.getState().reset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders nothing when step is not uploading', () => {
    const { container } = renderWithProviders(<UploadProgress />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders progress bar and uploading text when step is uploading', () => {
    useUploadStore.setState({ step: 'uploading', uploadProgress: 45 });

    renderWithProviders(<UploadProgress />);

    expect(screen.getByText('Uploading document...')).toBeInTheDocument();
    expect(screen.getByText('45%')).toBeInTheDocument();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('displays a spinner animation', () => {
    useUploadStore.setState({ step: 'uploading', uploadProgress: 0 });

    renderWithProviders(<UploadProgress />);

    const spinner = document.querySelector('svg.animate-spin');
    expect(spinner).toBeInTheDocument();
  });

  it('shows the progress bar with the current upload percentage', () => {
    useUploadStore.setState({ step: 'uploading', uploadProgress: 72 });

    renderWithProviders(<UploadProgress />);

    expect(screen.getByText('72%')).toBeInTheDocument();
    // The Progress component from shadcn/ui uses role="progressbar"
    const progressBar = screen.getByRole('progressbar');
    expect(progressBar).toBeInTheDocument();
  });

  it('does not show cold-start message before 3 seconds', () => {
    useUploadStore.setState({ step: 'uploading', uploadProgress: 10 });

    renderWithProviders(<UploadProgress />);

    // Advance 2.9 seconds — should not show cold start message
    act(() => {
      vi.advanceTimersByTime(2999);
    });

    expect(screen.queryByText('Starting up, this may take a moment...')).not.toBeInTheDocument();
  });

  it('shows cold-start message after 3 seconds', () => {
    useUploadStore.setState({ step: 'uploading', uploadProgress: 10 });

    renderWithProviders(<UploadProgress />);

    // Advance exactly 3 seconds
    act(() => {
      vi.advanceTimersByTime(3000);
    });

    expect(screen.getByText('Starting up, this may take a moment...')).toBeInTheDocument();
  });

  it('hides cold-start message when step changes from uploading', () => {
    useUploadStore.setState({ step: 'uploading', uploadProgress: 10 });

    const { rerender } = renderWithProviders(<UploadProgress />);

    // Trigger cold-start message
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.getByText('Starting up, this may take a moment...')).toBeInTheDocument();

    // Transition away from uploading
    act(() => {
      useUploadStore.setState({ step: 'processing' });
    });

    rerender(<TranslationProvider><UploadProgress /></TranslationProvider>);

    expect(screen.queryByText('Starting up, this may take a moment...')).not.toBeInTheDocument();
    expect(screen.queryByText('Uploading document...')).not.toBeInTheDocument();
  });

  it('updates displayed percentage when uploadProgress changes', () => {
    useUploadStore.setState({ step: 'uploading', uploadProgress: 25 });

    const { rerender } = renderWithProviders(<UploadProgress />);
    expect(screen.getByText('25%')).toBeInTheDocument();

    act(() => {
      useUploadStore.setState({ uploadProgress: 80 });
    });

    rerender(<TranslationProvider><UploadProgress /></TranslationProvider>);
    expect(screen.getByText('80%')).toBeInTheDocument();
  });

  it('has accessible role and aria-live for screen readers', () => {
    useUploadStore.setState({ step: 'uploading', uploadProgress: 50 });

    renderWithProviders(<UploadProgress />);

    const statusRegion = screen.getByRole('status');
    expect(statusRegion).toHaveAttribute('aria-live', 'polite');
  });
});
