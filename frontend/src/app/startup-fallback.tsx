import { useCallback, useSyncExternalStore } from 'react';
import { notifyManager } from '@tanstack/react-query';
import { useHydrated, useRouter, useRouterState } from '@tanstack/react-router';

import type { SessionInfo } from '@/common/api/generated/data-contracts';
import { queryKeys } from '@/common/api/query-keys';
import { AppLayout } from '@/common/components/layout/app-layout';
import { AppShellSkeleton } from '@/common/components/layout/app-shell-skeleton';
import {
  SkeletonRegion,
  SkeletonRows,
} from '@/common/components/loading-skeleton';
import { Skeleton } from '@/common/components/ui/skeleton';
import { LoginPageSkeleton } from '@/modules/auth/loading';
import { FeedPageSkeleton, ResultPageSkeleton } from '@/modules/public/loading';

export function NeutralFallback() {
  return (
    <SkeletonRegion
      label="Opening Morgenruf…"
      className="grid min-h-dvh place-items-center p-4"
    >
      <div className="w-64 space-y-4">
        <Skeleton className="mx-auto size-12 rounded-xl" />
        <Skeleton className="h-5 w-full" />
        <Skeleton className="mx-auto h-4 w-40" />
      </div>
    </SkeletonRegion>
  );
}

/** Both branches are static so every URL can hydrate the same request-free shell. */
export function DocumentFallback() {
  return (
    <>
      <div data-startup-dashboard="">
        <AppShellSkeleton>
          <div className="page">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0 space-y-3">
                <Skeleton className="h-7 w-40" />
                <Skeleton className="h-4 w-64 max-w-full" />
              </div>

              <Skeleton className="h-9 w-24 shrink-0" />
            </div>

            <SkeletonRows />
          </div>
        </AppShellSkeleton>
      </div>

      <div data-startup-public="">
        <NeutralFallback />
      </div>
    </>
  );
}

export function StartupFallback() {
  const hydrated = useHydrated();
  const router = useRouter();
  const location = useRouterState({ select: (state) => state.location });

  const client = router.options.context.services.queryClient;
  const session = useSyncExternalStore(
    useCallback(
      (onChange: () => void) =>
        client.getQueryCache().subscribe(notifyManager.batchCalls(onChange)),
      [client],
    ),
    () => client.getQueryData<SessionInfo>(queryKeys.session),
    () => undefined,
  );

  if (!hydrated) return <DocumentFallback />;

  if (location.pathname === '/dashboard/login') return <LoginPageSkeleton />;
  if (location.pathname.startsWith('/feed/')) return <FeedPageSkeleton />;

  if (
    ['/auth/result', '/email/result', '/connect/zoom/result'].includes(
      location.pathname,
    )
  )
    return <ResultPageSkeleton />;

  const metadata = router
    .matchRoutes(location.pathname, location.search)
    .filter((match) => match.staticData.workspace)
    .at(-1)?.staticData.workspace;

  if (metadata) {
    const PageSkeleton = metadata.Skeleton;

    if (session)
      return (
        <AppLayout
          title={metadata.title}
          loadingFallback={<PageSkeleton />}
          requirement={metadata}
          pendingView={{ title: metadata.title, content: <PageSkeleton /> }}
        />
      );

    return (
      <AppShellSkeleton>
        <PageSkeleton />
      </AppShellSkeleton>
    );
  }

  return <DocumentFallback />;
}

/** Leaf fallbacks use the same neutral first render without nesting an app shell. */
export function PagePending() {
  const hydrated = useHydrated();
  const router = useRouter();
  const location = useRouterState({ select: (state) => state.location });

  if (!hydrated) return <NeutralFallback />;

  if (location.pathname === '/dashboard/login') return <LoginPageSkeleton />;
  if (location.pathname.startsWith('/feed/')) return <FeedPageSkeleton />;

  if (
    ['/auth/result', '/email/result', '/connect/zoom/result'].includes(
      location.pathname,
    )
  )
    return <ResultPageSkeleton />;

  const metadata = router
    .matchRoutes(location.pathname, location.search)
    .filter((match) => match.staticData.workspace)
    .at(-1)?.staticData.workspace;
  const PageSkeleton = metadata?.Skeleton;

  return PageSkeleton ? <PageSkeleton /> : <NeutralFallback />;
}
