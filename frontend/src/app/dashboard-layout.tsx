import { matchRoutes, useLocation, useNavigation } from 'react-router';

import { AppLayout } from '@/common/components/layout/app-layout';
import { AppShellSkeleton } from '@/common/components/layout/app-shell-skeleton';
import { StandupsPageSkeleton } from '@/modules/standups/loading';

import { dashboardRoutes, type LoadingRouteHandle } from './dashboard-routes';

function dashboardLoadingView(pathname: string) {
  const handle = matchRoutes(dashboardRoutes, pathname, '/dashboard')?.at(-1)
    ?.route.handle as LoadingRouteHandle | undefined;
  const Skeleton = handle?.Skeleton ?? StandupsPageSkeleton;

  return { title: handle?.title ?? 'Standups', content: <Skeleton /> };
}

export function DashboardHydrateFallback() {
  const location = useLocation();
  return (
    <AppShellSkeleton>
      {dashboardLoadingView(location.pathname).content}
    </AppShellSkeleton>
  );
}

export function DashboardLayout() {
  const location = useLocation();
  const navigation = useNavigation();
  const current = dashboardLoadingView(location.pathname);
  const destination = navigation.location;
  // Filter and dialog URL changes should preserve the current form and page.
  const pending =
    destination &&
    destination.pathname !== location.pathname &&
    matchRoutes(dashboardRoutes, destination, '/dashboard');

  return (
    <AppLayout
      title={current.title}
      loadingFallback={current.content}
      pendingView={
        pending ? dashboardLoadingView(destination.pathname) : undefined
      }
    />
  );
}
