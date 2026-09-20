import {
  SkeletonPage,
  SkeletonRegion,
} from '@/common/components/loading-skeleton';
import { Skeleton } from '@/common/components/ui/skeleton';

export function StandupsSkeleton() {
  return (
    <SkeletonRegion label="Loading standups…">
      <div className="space-y-4">
        <div className="flex flex-col justify-between gap-3 sm:flex-row">
          <Skeleton className="h-10 w-60" />
          <Skeleton className="h-9 w-full sm:w-64" />
        </div>
        <Skeleton className="h-3 w-44" />
        <div className="divide-y rounded-xl border bg-card">
          {[0, 1, 2].map((row) => (
            <div
              key={row}
              className="grid gap-4 p-4 sm:grid-cols-2 sm:p-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)_minmax(0,1fr)_auto] lg:gap-5"
            >
              {[0, 1, 2].map((column) => (
                <div key={column} className="space-y-2">
                  <Skeleton className="h-4 w-32 max-w-full" />
                  <Skeleton className="h-3 w-40 max-w-full" />
                  <Skeleton className="h-3 w-28 max-w-full" />
                </div>
              ))}
              <Skeleton className="h-8 w-24" />
            </div>
          ))}
        </div>
      </div>
    </SkeletonRegion>
  );
}

export function StandupsPageSkeleton() {
  return (
    <SkeletonPage title="Standups" reserveActionSpace>
      <StandupsSkeleton />
    </SkeletonPage>
  );
}
