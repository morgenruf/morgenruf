import {
  SkeletonCard,
  SkeletonFields,
  SkeletonPage,
  SkeletonPeople,
  SkeletonRegion,
  SkeletonRows,
  SkeletonStats,
  SkeletonTable,
  SkeletonText,
} from '@/common/components/loading-skeleton';
import { Skeleton } from '@/common/components/ui/skeleton';

export function AttendanceSkeleton() {
  return (
    <SkeletonRegion label="Loading attendance…">
      <div className="space-y-6">
        <Skeleton className="h-4 w-64 max-w-full" />
        <SkeletonStats icons />
        <SkeletonCard>
          <Skeleton className="h-64 w-full rounded-lg sm:h-72" />
          <Skeleton className="mt-4 h-12 w-full rounded-lg" />
        </SkeletonCard>
        <div className="grid gap-5 xl:grid-cols-2">
          <SkeletonCard>
            <SkeletonPeople rows={3} />
          </SkeletonCard>
          <SkeletonCard>
            <SkeletonTable columns={5} />
          </SkeletonCard>
        </div>
      </div>
    </SkeletonRegion>
  );
}

export function ConnectListSkeleton() {
  return (
    <SkeletonRegion label="Loading coffee chats…">
      <div className="space-y-6">
        <SkeletonRows rows={2} />
        <Skeleton className="h-5 w-60 max-w-full" />
        <AttendanceSkeleton />
      </div>
    </SkeletonRegion>
  );
}

export function ProgramFormSkeleton() {
  return (
    <SkeletonRegion label="Loading coffee chat form…">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <SkeletonCard>
          <div className="space-y-6">
            <div className="flex flex-wrap gap-2">
              {Array.from({ length: 5 }, (_, index) => (
                <Skeleton key={index} className="h-8 w-20" />
              ))}
            </div>
            <SkeletonFields count={6} />
            <SkeletonText />
            <Skeleton className="h-9 w-36" />
          </div>
        </SkeletonCard>
        <SkeletonCard>
          <div className="space-y-5">
            <SkeletonPeople rows={1} />
            <SkeletonText lines={5} />
          </div>
        </SkeletonCard>
      </div>
    </SkeletonRegion>
  );
}

export function ConnectDetailSkeleton() {
  return (
    <SkeletonRegion label="Loading coffee chat…">
      <div className="space-y-6">
        <div className="space-y-2">
          <Skeleton className="h-7 w-64 max-w-full" />
          <Skeleton className="h-4 w-48" />
        </div>
        <ProgramFormSkeleton />
      </div>
    </SkeletonRegion>
  );
}

export function ConnectAttendanceSkeleton() {
  return (
    <SkeletonRegion label="Loading attendance…">
      <div className="space-y-6">
        <div className="max-w-sm">
          <SkeletonFields count={1} />
        </div>
        <AttendanceSkeleton />
      </div>
    </SkeletonRegion>
  );
}

export function ConnectListPageSkeleton() {
  return (
    <SkeletonPage title="Coffee chats">
      <ConnectListSkeleton />
    </SkeletonPage>
  );
}
export function ConnectNewPageSkeleton() {
  return (
    <SkeletonPage title="New coffee chat">
      <ProgramFormSkeleton />
    </SkeletonPage>
  );
}
export function ConnectDetailPageSkeleton() {
  return (
    <div className="page">
      <Skeleton className="h-4 w-32" />
      <ConnectDetailSkeleton />
    </div>
  );
}
export function ConnectAttendancePageSkeleton() {
  return (
    <SkeletonPage title="Coffee chat attendance">
      <ConnectAttendanceSkeleton />
    </SkeletonPage>
  );
}
