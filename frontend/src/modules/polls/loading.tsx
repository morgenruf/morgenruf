import {
  SkeletonCard,
  SkeletonPage,
  SkeletonRegion,
  SkeletonTable,
} from '@/common/components/loading-skeleton';

export function PollsListSkeleton() {
  return (
    <SkeletonRegion label="Loading polls…">
      <SkeletonTable columns={5} rows={4} />
    </SkeletonRegion>
  );
}

export function PollsPageSkeleton() {
  return (
    <SkeletonPage title="Polls">
      <SkeletonCard>
        <PollsListSkeleton />
      </SkeletonCard>
    </SkeletonPage>
  );
}
