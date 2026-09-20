import {
  SkeletonCard,
  SkeletonChart,
  SkeletonPage,
  SkeletonRegion,
  SkeletonStats,
  SkeletonTable,
} from '@/common/components/loading-skeleton';
import { Skeleton } from '@/common/components/ui/skeleton';

export function AnalyticsSkeleton() {
  return (
    <SkeletonRegion label="Loading analytics…">
      <div className="space-y-6">
        <SkeletonStats className="lg:grid-cols-2 xl:grid-cols-4" />
        <SkeletonCard>
          <SkeletonChart />
        </SkeletonCard>
        <SkeletonCard>
          <SkeletonTable columns={5} />
        </SkeletonCard>
      </div>
    </SkeletonRegion>
  );
}

export function AnalyticsPageSkeleton() {
  return (
    <SkeletonPage className="page-wide" title="Analytics" reserveActionSpace>
      <div className="space-y-6">
        <div className="flex flex-wrap items-center gap-4">
          <Skeleton className="h-9 w-56" />
          <Skeleton className="h-4 w-40" />
        </div>
        <AnalyticsSkeleton />
      </div>
    </SkeletonPage>
  );
}
