import {
  SkeletonCard,
  SkeletonChart,
  SkeletonRegion,
  SkeletonStats,
  SkeletonTable,
} from '@/common/components/loading-skeleton';
import { PageHeader } from '@/common/components/page';
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
    <div className="page [&>header>h1]:shrink-0">
      <PageHeader
        title="Analytics"
        reserveActionSpace
        description="Participation, blockers, and standup health."
      />
      <SkeletonRegion label="Loading analytics…">
        <div className="space-y-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-center">
            <div className="w-full min-w-0 sm:w-56">
              <Skeleton className="h-9 w-full" />
            </div>
            <div className="w-full min-w-0 sm:w-40">
              <Skeleton className="h-9 w-full" />
            </div>
            <div className="flex h-9 shrink-0 items-center gap-3 sm:ml-auto">
              <Skeleton className="h-3 w-28" />
              <Skeleton className="h-[16.6px] w-7 rounded-full" />
            </div>
          </div>
          <AnalyticsSkeleton />
        </div>
      </SkeletonRegion>
    </div>
  );
}
