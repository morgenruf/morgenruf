import {
  SkeletonCard,
  SkeletonPeople,
  SkeletonRegion,
  SkeletonStats,
} from '@/common/components/loading-skeleton';
import { Skeleton } from '@/common/components/ui/skeleton';

import { TodayPageHeader } from './today-page-header';

export function TodaySkeleton() {
  return (
    <SkeletonRegion label="Loading today…">
      <div className="space-y-6">
        <SkeletonStats
          icons
          count={3}
          className="sm:grid-cols-3 lg:grid-cols-3"
        />
        <div className="grid items-start gap-6 lg:grid-cols-[1.5fr_1fr]">
          <SkeletonCard>
            <SkeletonPeople rows={5} />
          </SkeletonCard>
          <div className="space-y-6">
            <SkeletonCard>
              <SkeletonPeople rows={3} />
            </SkeletonCard>
            <SkeletonCard />
          </div>
        </div>
      </div>
    </SkeletonRegion>
  );
}

export function TodayPageSkeleton() {
  return (
    <div className="page">
      <TodayPageHeader
        description={<Skeleton className="h-4 w-72 max-w-full" />}
      />
      <TodaySkeleton />
    </div>
  );
}
