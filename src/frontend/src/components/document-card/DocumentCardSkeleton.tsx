import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

/**
 * Loading skeleton for the Document Card.
 * Mirrors the layout of DocumentCardView so the transition
 * from loading → content is visually seamless.
 */
export function DocumentCardSkeleton() {
  return (
    <div aria-live="polite" role="status" aria-label="Loading document card">
      <Card data-testid="document-card-skeleton">
        <CardHeader className="space-y-2">
          {/* Title */}
          <Skeleton className="h-7 w-3/4" />
          {/* Classification badge */}
          <Skeleton className="h-5 w-24 rounded-full" />
        </CardHeader>

        <CardContent className="space-y-4">
          {/* Summary (2-3 lines) */}
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </div>

          {/* Statistics section */}
          <div className="grid grid-cols-2 gap-3">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-12" />
          </div>

          {/* File metadata */}
          <div className="flex gap-3">
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-12" />
            <Skeleton className="h-4 w-10" />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
