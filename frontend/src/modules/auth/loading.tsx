import {
  SkeletonRegion,
  SkeletonText,
} from '@/common/components/loading-skeleton';
import { Card, CardContent, CardHeader } from '@/common/components/ui/card';
import { Skeleton } from '@/common/components/ui/skeleton';

export function LoginPageSkeleton() {
  return (
    <div className="grid min-h-dvh place-items-center px-4">
      <SkeletonRegion label="Loading sign in…" className="w-full max-w-sm">
        <div className="mb-7 flex items-center justify-center gap-2">
          <Skeleton className="size-10" />
          <Skeleton className="h-6 w-28" />
        </div>
        <Card className="py-6">
          <CardHeader className="gap-4 px-6">
            <Skeleton className="mx-auto h-7 w-60 max-w-full" />
            <SkeletonText />
          </CardHeader>
          <CardContent className="mt-3 space-y-4 px-6">
            <Skeleton className="h-10 w-full" />
            <SkeletonText lines={2} />
          </CardContent>
        </Card>
      </SkeletonRegion>
    </div>
  );
}
