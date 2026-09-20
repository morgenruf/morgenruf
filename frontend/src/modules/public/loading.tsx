import {
  SkeletonCard,
  SkeletonRegion,
  SkeletonResponse,
  SkeletonText,
} from '@/common/components/loading-skeleton';
import { Card, CardContent, CardHeader } from '@/common/components/ui/card';
import { Skeleton } from '@/common/components/ui/skeleton';

export function FeedSkeleton() {
  return (
    <SkeletonRegion label="Loading standup report…">
      <div className="space-y-6">
        <div className="space-y-2">
          <Skeleton className="h-7 w-60 max-w-full" />
          <Skeleton className="h-4 w-36" />
        </div>
        {Array.from({ length: 3 }, (_, index) => (
          <SkeletonCard key={index}>
            <SkeletonResponse />
          </SkeletonCard>
        ))}
      </div>
    </SkeletonRegion>
  );
}
export function FeedPageSkeleton() {
  return (
    <div className="page max-w-3xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Skeleton className="size-8" />
          <span className="font-semibold">Morgenruf</span>
        </div>
        <Skeleton className="size-8" />
      </div>
      <FeedSkeleton />
    </div>
  );
}
export function ResultPageSkeleton() {
  return (
    <div className="grid min-h-dvh place-items-center p-4">
      <SkeletonRegion label="Loading result…" className="w-full max-w-md">
        <Card className="py-6">
          <CardHeader className="items-center gap-3">
            <Skeleton className="mb-3 size-9 rounded-full" />
            <Skeleton className="h-7 w-56 max-w-full" />
          </CardHeader>
          <CardContent className="space-y-5">
            <SkeletonText lines={2} />
            <Skeleton className="mx-auto h-9 w-40" />
          </CardContent>
        </Card>
      </SkeletonRegion>
    </div>
  );
}
