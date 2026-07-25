import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ConsentDialog } from '@/components/upload/ConsentDialog';
import { TranslationProvider } from '@/i18n';
import { useUploadStore } from '@/store/uploadStore';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

describe('ConsentDialog', () => {
  beforeEach(() => {
    useUploadStore.setState({
      step: 'idle',
      selectedFile: null,
      uploadProgress: 0,
      result: null,
      error: null,
      documentId: null,
    });
  });

  it('does not render dialog content when step is not consent-pending', () => {
    useUploadStore.setState({ step: 'idle' });
    renderWithProviders(<ConsentDialog />);
    expect(screen.queryByText('External Processing Notice')).not.toBeInTheDocument();
  });

  it('renders dialog content when step is consent-pending', () => {
    useUploadStore.setState({ step: 'consent-pending' });
    renderWithProviders(<ConsentDialog />);
    expect(screen.getByText('External Processing Notice')).toBeInTheDocument();
  });

  it('displays the consent body text', () => {
    useUploadStore.setState({ step: 'consent-pending' });
    renderWithProviders(<ConsentDialog />);
    expect(
      screen.getByText('Your document will be sent to an external AI service for analysis.'),
    ).toBeInTheDocument();
  });

  it('displays all three data handling bullet points from i18n', () => {
    useUploadStore.setState({ step: 'consent-pending' });
    renderWithProviders(<ConsentDialog />);
    expect(
      screen.getByText('Only the document text and system prompts are sent.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('No personal data or usage history is transmitted.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Document content is not retained beyond the analysis session.'),
    ).toBeInTheDocument();
  });

  it('displays accept and cancel buttons with correct i18n text', () => {
    useUploadStore.setState({ step: 'consent-pending' });
    renderWithProviders(<ConsentDialog />);
    expect(screen.getByRole('button', { name: 'I understand, proceed' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  it('calls acceptConsent when accept button is clicked', () => {
    useUploadStore.setState({
      step: 'consent-pending',
      selectedFile: { file: new File(['x'], 'test.md'), name: 'test.md', size: 1, format: 'markdown' },
    });
    const acceptConsentSpy = vi.fn();
    useUploadStore.setState({ acceptConsent: acceptConsentSpy } as any);

    renderWithProviders(<ConsentDialog />);
    fireEvent.click(screen.getByRole('button', { name: 'I understand, proceed' }));
    expect(acceptConsentSpy).toHaveBeenCalledTimes(1);
  });

  it('calls declineConsent when cancel button is clicked', () => {
    useUploadStore.setState({ step: 'consent-pending' });
    const declineConsentSpy = vi.fn();
    useUploadStore.setState({ declineConsent: declineConsentSpy } as any);

    renderWithProviders(<ConsentDialog />);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(declineConsentSpy).toHaveBeenCalledTimes(1);
  });

  it('calls declineConsent when close (X) button is clicked', () => {
    useUploadStore.setState({ step: 'consent-pending' });
    const declineConsentSpy = vi.fn();
    useUploadStore.setState({ declineConsent: declineConsentSpy } as any);

    renderWithProviders(<ConsentDialog />);
    // The close button has sr-only text "Close"
    const closeButton = screen.getByRole('button', { name: 'Close' });
    fireEvent.click(closeButton);
    expect(declineConsentSpy).toHaveBeenCalledTimes(1);
  });

  it('calls declineConsent when Escape key is pressed', () => {
    useUploadStore.setState({ step: 'consent-pending' });
    const declineConsentSpy = vi.fn();
    useUploadStore.setState({ declineConsent: declineConsentSpy } as any);

    renderWithProviders(<ConsentDialog />);
    // Escape key triggers onOpenChange(false) in Radix Dialog
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(declineConsentSpy).toHaveBeenCalled();
  });
});
