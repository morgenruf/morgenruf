import { useRouter, useRouterState } from '@tanstack/react-router';

import { AppLayout } from '@/common/components/layout/app-layout';
import { AppShellSkeleton } from '@/common/components/layout/app-shell-skeleton';
import type { DashboardRouteMetadata } from '@/common/routing/metadata';

import { dashboardViews } from './dashboard-routes';

function view(
  matches: ReadonlyArray<{
    staticData: { workspace?: DashboardRouteMetadata };
  }>,
) {
  return (
    matches.filter((match) => match.staticData.workspace).at(-1)?.staticData
      .workspace ?? dashboardViews.standups
  );
}

export function DashboardHydrateFallback() {
  const router = useRouter();
  const location = useRouterState({ select: (state) => state.location });
  const { Skeleton } = view(
    router.matchRoutes(location.pathname, location.search),
  );

  return (
    <AppShellSkeleton>
      <Skeleton />
    </AppShellSkeleton>
  );
}

export function DashboardLayout() {
  const router = useRouter();
  const state = useRouterState({
    select: (state) => ({
      matches: state.matches,
      status: state.status,
      location: state.location,
      resolvedLocation: state.resolvedLocation,
    }),
  });

  const current = view(state.matches);
  const destination =
    state.status === 'pending' &&
    state.location.pathname !== state.resolvedLocation?.pathname
      ? view(router.matchRoutes(state.location.pathname, state.location.search))
      : undefined;
  const Skeleton = current.Skeleton;
  const PendingSkeleton = destination?.Skeleton;

  return (
    <AppLayout
      title={current.title}
      loadingFallback={<Skeleton />}
      requirement={current}
      pendingView={
        destination && PendingSkeleton
          ? { title: destination.title, content: <PendingSkeleton /> }
          : undefined
      }
    />
  );
}
