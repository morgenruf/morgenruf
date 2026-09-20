import {
  SkeletonCard,
  SkeletonFields,
  SkeletonPage,
  SkeletonPeople,
  SkeletonRegion,
  SkeletonResponse,
  SkeletonTable,
} from '@/common/components/loading-skeleton';
import { Card, CardContent } from '@/common/components/ui/card';
import { Skeleton } from '@/common/components/ui/skeleton';

export function ReportsSkeleton() {
  return (
    <SkeletonRegion label="Loading reports…">
      <div className="space-y-6">
        <SkeletonCard>
          <SkeletonTable columns={3} />
        </SkeletonCard>
        <SkeletonCard>
          <div className="space-y-6">
            <SkeletonPeople rows={1} />
            <SkeletonResponse />
          </div>
        </SkeletonCard>
      </div>
    </SkeletonRegion>
  );
}

export function ReportsPageSkeleton() {
  return (
    <SkeletonPage title="Reports">
      <div className="space-y-6">
        <Card>
          <CardContent className="space-y-4">
            <SkeletonFields count={3} className="sm:grid-cols-3" />
            <div className="flex gap-2">
              <Skeleton className="h-8 w-24" />
              <Skeleton className="h-8 w-24" />
            </div>
          </CardContent>
        </Card>
        <ReportsSkeleton />
      </div>
    </SkeletonPage>
  );
}
