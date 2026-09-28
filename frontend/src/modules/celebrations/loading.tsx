import {
  SkeletonCard,
  SkeletonFields,
  SkeletonPage,
  SkeletonRegion,
  SkeletonRows,
} from '@/common/components/loading-skeleton';
import { Skeleton } from '@/common/components/ui/skeleton';

export function CelebrationSettingsSkeleton() {
  return (
    <SkeletonRegion label="Loading celebrations…">
      <div className="max-w-2xl space-y-4">
        <SkeletonFields />
        <Skeleton className="h-9 w-28" />
      </div>
    </SkeletonRegion>
  );
}

export function HolidaysSkeleton() {
  return (
    <SkeletonRegion label="Loading holidays…">
      <SkeletonRows rows={3} />
    </SkeletonRegion>
  );
}

export function UpcomingSkeleton() {
  return (
    <SkeletonRegion label="Loading upcoming celebrations…">
      <SkeletonRows rows={3} />
    </SkeletonRegion>
  );
}

export function CelebrationsPageSkeleton() {
  return (
    <SkeletonPage title="Celebrations" reserveActionSpace>
      <div className="space-y-6">
        <SkeletonCard>
          <CelebrationSettingsSkeleton />
        </SkeletonCard>
        <div className="grid gap-5 md:grid-cols-2">
          <SkeletonCard>
            <HolidaysSkeleton />
          </SkeletonCard>
          <SkeletonCard>
            <UpcomingSkeleton />
          </SkeletonCard>
        </div>
      </div>
    </SkeletonPage>
  );
}
