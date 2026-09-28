import {
  SkeletonCard,
  SkeletonFields,
  SkeletonPage,
  SkeletonRegion,
} from '@/common/components/loading-skeleton';
import { Skeleton } from '@/common/components/ui/skeleton';

export function ProfileFormSkeleton() {
  return (
    <SkeletonRegion label="Loading your profile…">
      <div className="max-w-2xl space-y-4">
        <SkeletonFields />
        <Skeleton className="h-9 w-28" />
      </div>
    </SkeletonRegion>
  );
}

export function ProfilePageSkeleton() {
  return (
    <SkeletonPage title="My profile">
      <SkeletonCard>
        <ProfileFormSkeleton />
      </SkeletonCard>
    </SkeletonPage>
  );
}
