import {
  SkeletonPage,
  SkeletonRegion,
  SkeletonRows,
} from '@/common/components/loading-skeleton';

export function StandupsSkeleton() {
  return (
    <SkeletonRegion label="Loading standups…">
      <SkeletonRows />
    </SkeletonRegion>
  );
}

export function StandupsPageSkeleton() {
  return (
    <SkeletonPage title="Standups">
      <StandupsSkeleton />
    </SkeletonPage>
  );
}
