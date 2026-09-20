import type { ReactNode } from 'react';

import { SkeletonRegion } from '@/common/components/loading-skeleton';
import { Skeleton } from '@/common/components/ui/skeleton';

import { AppMain } from './app-main';

export function AppShellSkeleton({ children }: { children: ReactNode }) {
  return (
    <SkeletonRegion
      label="Opening your workspace…"
      className="h-dvh overflow-hidden"
      contentClassName="h-full"
    >
      <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col border-r bg-sidebar md:flex **:data-[slot=skeleton]:bg-sidebar-foreground/10 dark:**:data-[slot=skeleton]:bg-muted">
        <div className="flex h-16 items-center gap-2 px-4">
          <Skeleton className="size-8" />
          <Skeleton className="h-5 w-32" />
        </div>
        <div className="min-h-0 flex-1 space-y-2 overflow-hidden px-4 py-1">
          {[1, 4, 3, 4].map((count, group) => (
            <div key={group} className="space-y-px">
              {group > 0 && (
                <div className="flex h-8 items-center">
                  <Skeleton className="h-3 w-16" />
                </div>
              )}
              {Array.from({ length: count }, (_, index) => (
                <div key={index} className="flex h-8 items-center gap-2">
                  <Skeleton className="size-4" />
                  <Skeleton className="h-4 w-28" />
                </div>
              ))}
            </div>
          ))}
        </div>
        <div className="shrink-0 p-2">
          <Skeleton className="h-8 w-full" />
        </div>
        <div className="border-t p-2">
          <Skeleton className="h-8 w-full" />
        </div>
      </aside>
      <div className="flex h-full min-w-0 flex-col md:pl-64">
        <div className="flex h-14 shrink-0 items-center gap-3 border-b px-4">
          <Skeleton className="size-6" />
          <Skeleton className="h-4 w-32" />
          <Skeleton className="ml-auto size-8" />
        </div>
        <AppMain>{children}</AppMain>
      </div>
    </SkeletonRegion>
  );
}
