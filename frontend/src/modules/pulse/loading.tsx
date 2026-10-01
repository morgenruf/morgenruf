import {
  SkeletonCard,
  SkeletonChart,
  SkeletonFields,
  SkeletonPage,
  SkeletonRegion,
} from '@/common/components/loading-skeleton';

export function PulseSettingsSkeleton() {
  return (
    <SkeletonRegion label="Loading pulse settings…">
      <SkeletonFields />
    </SkeletonRegion>
  );
}

export function PulseTrendSkeleton() {
  return (
    <SkeletonRegion label="Loading pulse…">
      <SkeletonChart className="h-64" />
    </SkeletonRegion>
  );
}

export function PulsePageSkeleton() {
  return (
    <SkeletonPage title="Pulse">
      <div className="space-y-6">
        <SkeletonCard>
          <PulseTrendSkeleton />
        </SkeletonCard>
        <SkeletonCard>
          <PulseSettingsSkeleton />
        </SkeletonCard>
      </div>
    </SkeletonPage>
  );
}
