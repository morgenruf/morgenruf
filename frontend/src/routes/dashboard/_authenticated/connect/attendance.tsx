import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import { ConnectAttendancePage } from '@/modules/connect/pages';
import { validateSearch } from '@/modules/connect/search';

export const Route = createFileRoute(
  '/dashboard/_authenticated/connect/attendance',
)({
  staticData: { workspace: dashboardViews.connectAttendance },
  beforeLoad: capabilityGuard(dashboardViews.connectAttendance),

  validateSearch,
  loaderDeps: ({ search }) => ({ program: search.program }),
  loader: ({ context, deps, abortController }) =>
    prefetchDashboard(
      context,
      'connectAttendance',
      deps,
      abortController.signal,
    ),

  pendingComponent: PagePending,
  component: ConnectAttendancePage,
});
