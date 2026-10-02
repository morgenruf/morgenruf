import {
  SkeletonCard,
  SkeletonPage,
  SkeletonRegion,
  SkeletonTable,
} from '@/common/components/loading-skeleton';

export function WatercoolerPageSkeleton() {
  return (
    <SkeletonPage title="Watercooler">
      <SkeletonCard>
        <SkeletonRegion label="Loading watercooler…">
          <SkeletonTable columns={4} rows={3} />
        </SkeletonRegion>
      </SkeletonCard>
    </SkeletonPage>
  );
}
