import {
  SkeletonCard,
  SkeletonPage,
  SkeletonPeople,
  SkeletonRegion,
  SkeletonStats,
} from '@/common/components/loading-skeleton';

export function TodaySkeleton() {
  return (
    <SkeletonRegion label="Loading today…">
      <div className="space-y-6">
        <SkeletonStats count={3} className="sm:grid-cols-3 lg:grid-cols-3" />
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
  const hour = new Date().getHours();
  return (
    <SkeletonPage
      title={
        hour < 12
          ? 'Good morning'
          : hour < 18
            ? 'Good afternoon'
            : 'Good evening'
      }
    >
      <TodaySkeleton />
    </SkeletonPage>
  );
}
