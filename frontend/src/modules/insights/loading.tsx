import {
  SkeletonCard,
  SkeletonPage,
  SkeletonPeople,
  SkeletonRegion,
} from '@/common/components/loading-skeleton';

export function InsightsSkeleton() {
  return (
    <SkeletonRegion label="Loading insights…">
      <div className="space-y-6">
        <SkeletonCard>
          <SkeletonPeople />
        </SkeletonCard>
        <SkeletonCard>
          <SkeletonPeople rows={3} />
        </SkeletonCard>
      </div>
    </SkeletonRegion>
  );
}

export function InsightsPageSkeleton() {
  return (
    <SkeletonPage title="Insights">
      <InsightsSkeleton />
    </SkeletonPage>
  );
}
