import {
  SkeletonCard,
  SkeletonPage,
  SkeletonRegion,
  SkeletonText,
} from '@/common/components/loading-skeleton';
import { Skeleton } from '@/common/components/ui/skeleton';

export function AutomationSkeleton() {
  return (
    <SkeletonRegion label="Loading automation…">
      <div className="grid gap-4 md:grid-cols-2">
        {Array.from({ length: 4 }, (_, index) => (
          <SkeletonCard key={index}>
            <div className="space-y-3">
              <SkeletonText />
              <Skeleton className="h-8 w-24" />
            </div>
          </SkeletonCard>
        ))}
      </div>
    </SkeletonRegion>
  );
}

export function AutomationPageSkeleton() {
  return (
    <SkeletonPage title="Automation">
      <AutomationSkeleton />
    </SkeletonPage>
  );
}
