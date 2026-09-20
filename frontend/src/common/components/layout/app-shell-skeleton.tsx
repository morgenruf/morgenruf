import type { ReactNode } from 'react';

import { SkeletonRegion } from '@/common/components/loading-skeleton';
import { Skeleton } from '@/common/components/ui/skeleton';

export function AppShellSkeleton({ children }: { children: ReactNode }) {
  return (
    <SkeletonRegion label="Opening your workspace…" className="min-h-dvh">
      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col border-r bg-sidebar md:flex **:data-[slot=skeleton]:bg-sidebar-foreground/10 dark:**:data-[slot=skeleton]:bg-muted">
        <div className="flex h-16 items-center gap-3 px-3">
          <Skeleton className="size-8" />
          <Skeleton className="h-5 w-32" />
        </div>
        <div className="flex-1 space-y-6 px-4 py-3">
          {[1, 4, 3, 4].map((count, group) => (
            <div key={group} className="space-y-3">
              <Skeleton className="h-3 w-16" />
              {Array.from({ length: count }, (_, index) => (
                <div key={index} className="flex items-center gap-3">
                  <Skeleton className="size-5" />
                  <Skeleton className="h-5 w-28" />
                </div>
              ))}
            </div>
          ))}
        </div>
        <div className="border-t p-4">
          <Skeleton className="h-9 w-full" />
        </div>
      </aside>
      <div className="md:pl-60">
        <div className="flex h-14 items-center gap-3 border-b px-4">
          <Skeleton className="size-8" />
          <Skeleton className="h-4 w-32" />
          <Skeleton className="ml-auto size-8" />
        </div>
        {children}
      </div>
    </SkeletonRegion>
  );
}
