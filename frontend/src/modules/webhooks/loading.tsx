import {
  SkeletonCard,
  SkeletonPage,
  SkeletonRegion,
  SkeletonText,
} from '@/common/components/loading-skeleton';
import { Skeleton } from '@/common/components/ui/skeleton';

export function WebhooksSkeleton() {
  return (
    <SkeletonRegion label="Loading webhooks…">
      <div className="space-y-4">
        {Array.from({ length: 3 }, (_, index) => (
          <SkeletonCard key={index}>
            <div className="space-y-4">
              <SkeletonText lines={2} />
              <div className="flex flex-wrap gap-2">
                <Skeleton className="h-8 w-24" />
                <Skeleton className="h-8 w-24" />
                <Skeleton className="h-8 w-24" />
              </div>
            </div>
          </SkeletonCard>
        ))}
      </div>
    </SkeletonRegion>
  );
}

export function WebhooksPageSkeleton() {
  return (
    <SkeletonPage title="Webhooks" reserveActionSpace>
      <WebhooksSkeleton />
    </SkeletonPage>
  );
}
