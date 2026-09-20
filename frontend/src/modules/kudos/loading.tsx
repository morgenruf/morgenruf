import {
  SkeletonCard,
  SkeletonFields,
  SkeletonPage,
  SkeletonPeople,
  SkeletonRegion,
  SkeletonText,
} from '@/common/components/loading-skeleton';
import { Card, CardContent } from '@/common/components/ui/card';
import { Skeleton } from '@/common/components/ui/skeleton';

export function KudosLeaderboardSkeleton() {
  return (
    <SkeletonRegion label="Loading leaderboard…">
      <SkeletonPeople rows={5} />
    </SkeletonRegion>
  );
}
export function KudosFeedSkeleton() {
  return (
    <SkeletonRegion label="Loading recognition…">
      <div className="space-y-3">
        {Array.from({ length: 3 }, (_, index) => (
          <Card key={index}>
            <CardContent className="space-y-3 pt-4">
              <div className="flex flex-wrap items-center gap-2">
                <Skeleton className="size-5 shrink-0 rounded-full" />
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-3 w-10" />
                <Skeleton className="size-5 shrink-0 rounded-full" />
                <Skeleton className="h-3 w-24" />
              </div>
              <SkeletonText lines={2} />
            </CardContent>
          </Card>
        ))}
      </div>
    </SkeletonRegion>
  );
}
export function KudosConfigSkeleton() {
  return (
    <SkeletonRegion label="Loading kudos settings…">
      <div className="max-w-lg space-y-4">
        <SkeletonFields />
        <Skeleton className="h-9 w-28" />
      </div>
    </SkeletonRegion>
  );
}
export function KudosPageSkeleton() {
  return (
    <SkeletonPage title="Kudos" reserveActionSpace>
      <div className="space-y-6">
        <SkeletonCard />
        <div className="grid gap-5 md:grid-cols-2">
          <SkeletonCard>
            <KudosLeaderboardSkeleton />
          </SkeletonCard>
          <SkeletonCard>
            <KudosLeaderboardSkeleton />
          </SkeletonCard>
        </div>
        <KudosFeedSkeleton />
        <SkeletonCard>
          <KudosConfigSkeleton />
        </SkeletonCard>
      </div>
    </SkeletonPage>
  );
}
