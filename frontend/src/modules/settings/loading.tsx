import {
  SkeletonCard,
  SkeletonFields,
  SkeletonPage,
  SkeletonRegion,
} from '@/common/components/loading-skeleton';
import { Skeleton } from '@/common/components/ui/skeleton';

export function FeatureSettingsSkeleton() {
  return (
    <SkeletonRegion label="Loading workspace features…">
      <div className="divide-y">
        {Array.from({ length: 5 }, (_, index) => (
          <div
            key={index}
            className="flex items-start justify-between gap-4 py-4 first:pt-0 last:pb-0"
          >
            <div className="min-w-0 flex-1 space-y-2">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-3 w-full" />
            </div>
            <Skeleton className="h-8 w-12 shrink-0" />
          </div>
        ))}
      </div>
    </SkeletonRegion>
  );
}

// Keep all three cards in the existing Settings grid during loading.
export function StandupSettingsSkeleton() {
  return (
    <SkeletonRegion
      label="Loading standup settings…"
      className="contents"
      contentClassName="contents"
    >
      <SkeletonCard>
        <SkeletonFields />
      </SkeletonCard>
      <SkeletonCard>
        <SkeletonFields count={2} />
      </SkeletonCard>
      <SkeletonCard>
        <SkeletonFields count={2} />
      </SkeletonCard>
    </SkeletonRegion>
  );
}
export function SettingsPageSkeleton() {
  return (
    <SkeletonPage title="Settings">
      <div className="grid gap-5 lg:grid-cols-2">
        <SkeletonCard>
          <FeatureSettingsSkeleton />
        </SkeletonCard>
        <SkeletonCard>
          <SkeletonFields />
        </SkeletonCard>
        <SkeletonCard>
          <SkeletonFields count={2} />
        </SkeletonCard>
        <SkeletonCard>
          <SkeletonFields count={2} />
        </SkeletonCard>
      </div>
    </SkeletonPage>
  );
}
