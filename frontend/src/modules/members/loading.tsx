import {
  SkeletonPage,
  SkeletonPeople,
  SkeletonRegion,
  SkeletonText,
} from '@/common/components/loading-skeleton';
import { Card, CardContent } from '@/common/components/ui/card';
import { Skeleton } from '@/common/components/ui/skeleton';

export function MembersSkeleton() {
  return (
    <SkeletonRegion label="Loading members…">
      <div className="space-y-4">
        <Skeleton className="h-4 w-36" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, index) => (
            <Card key={index}>
              <CardContent className="pt-5">
                <div className="space-y-4">
                  <SkeletonPeople rows={1} />
                  <SkeletonText />
                  <Skeleton className="h-8 w-28" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </SkeletonRegion>
  );
}

export function MembersPageSkeleton() {
  return (
    <SkeletonPage title="Members" reserveActionSpace>
      <div className="space-y-6">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {Array.from({ length: 5 }, (_, index) => (
            <Skeleton key={index} className="h-9 w-full" />
          ))}
        </div>
        <MembersSkeleton />
      </div>
    </SkeletonPage>
  );
}
