import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { DocumentCardSkeleton } from '@/components/document-card/DocumentCardSkeleton';

describe('DocumentCardSkeleton', () => {
  it('renders a loading skeleton card', () => {
    render(<DocumentCardSkeleton />);
    expect(screen.getByTestId('document-card-skeleton')).toBeInTheDocument();
  });

  it('has an ARIA live region for accessibility', () => {
    render(<DocumentCardSkeleton />);
    const liveRegion = screen.getByRole('status');
    expect(liveRegion).toHaveAttribute('aria-live', 'polite');
    expect(liveRegion).toHaveAttribute('aria-label', 'Loading document card');
  });

  it('renders skeleton elements for all card sections', () => {
    const { container } = render(<DocumentCardSkeleton />);
    // Skeleton elements use the animate-pulse class from the Skeleton component
    const skeletons = container.querySelectorAll('.animate-pulse');
    // Title + badge + 3 summary lines + 4 statistics + 3 metadata = 12
    expect(skeletons.length).toBe(12);
  });
});
