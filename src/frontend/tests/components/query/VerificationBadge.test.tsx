import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { VerificationBadge } from '@/components/query/VerificationBadge';
import { TranslationProvider } from '@/i18n';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

describe('VerificationBadge', () => {
  describe('verified state', () => {
    it('renders "Verified" text label when verified is true', () => {
      renderWithProviders(<VerificationBadge verified={true} />);

      expect(screen.getByText('Verified')).toBeInTheDocument();
    });

    it('renders with the verified data-testid', () => {
      renderWithProviders(<VerificationBadge verified={true} />);

      expect(screen.getByTestId('verification-badge-verified')).toBeInTheDocument();
    });

    it('renders a checkmark icon (svg with aria-hidden)', () => {
      renderWithProviders(<VerificationBadge verified={true} />);

      const badge = screen.getByTestId('verification-badge-verified');
      const svg = badge.querySelector('svg');
      expect(svg).toBeInTheDocument();
      expect(svg).toHaveAttribute('aria-hidden', 'true');
    });

    it('applies green styling classes', () => {
      renderWithProviders(<VerificationBadge verified={true} />);

      const badge = screen.getByTestId('verification-badge-verified');
      expect(badge.className).toContain('bg-green-100');
      expect(badge.className).toContain('text-green-800');
    });
  });

  describe('unverified state', () => {
    it('renders "Not verified" text label when verified is false', () => {
      renderWithProviders(<VerificationBadge verified={false} />);

      expect(screen.getByText('Not verified')).toBeInTheDocument();
    });

    it('renders with the unverified data-testid', () => {
      renderWithProviders(<VerificationBadge verified={false} />);

      expect(screen.getByTestId('verification-badge-unverified')).toBeInTheDocument();
    });

    it('renders a warning icon (svg with aria-hidden)', () => {
      renderWithProviders(<VerificationBadge verified={false} />);

      const badge = screen.getByTestId('verification-badge-unverified');
      const svg = badge.querySelector('svg');
      expect(svg).toBeInTheDocument();
      expect(svg).toHaveAttribute('aria-hidden', 'true');
    });

    it('applies amber styling classes', () => {
      renderWithProviders(<VerificationBadge verified={false} />);

      const badge = screen.getByTestId('verification-badge-unverified');
      expect(badge.className).toContain('bg-amber-100');
      expect(badge.className).toContain('text-amber-800');
    });
  });

  describe('accessibility', () => {
    it('has role="status" for screen reader announcements', () => {
      renderWithProviders(<VerificationBadge verified={true} />);

      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('is keyboard-focusable with tabIndex=0', () => {
      renderWithProviders(<VerificationBadge verified={true} />);

      const badge = screen.getByRole('status');
      expect(badge).toHaveAttribute('tabindex', '0');
    });

    it('has focus-visible ring styles for keyboard navigation', () => {
      renderWithProviders(<VerificationBadge verified={false} />);

      const badge = screen.getByRole('status');
      expect(badge.className).toContain('focus-visible:ring-2');
    });

    it('uses text labels (not color alone) to convey status', () => {
      renderWithProviders(<VerificationBadge verified={true} />);

      // Text label should be present regardless of color
      expect(screen.getByText('Verified')).toBeInTheDocument();
    });

    it('uses distinct icons for verified vs unverified', () => {
      const { unmount } = renderWithProviders(<VerificationBadge verified={true} />);
      const verifiedSvg = screen.getByTestId('verification-badge-verified').querySelector('svg path');
      const verifiedPath = verifiedSvg?.getAttribute('d');
      unmount();

      renderWithProviders(<VerificationBadge verified={false} />);
      const unverifiedSvg = screen.getByTestId('verification-badge-unverified').querySelector('svg path');
      const unverifiedPath = unverifiedSvg?.getAttribute('d');

      // The two icons should have different SVG paths
      expect(verifiedPath).not.toBe(unverifiedPath);
    });
  });

  describe('custom className', () => {
    it('merges additional className', () => {
      renderWithProviders(<VerificationBadge verified={true} className="ml-2" />);

      const badge = screen.getByRole('status');
      expect(badge.className).toContain('ml-2');
    });
  });
});
