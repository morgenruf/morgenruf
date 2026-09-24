import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import { ConnectDetailPage } from '@/modules/connect/pages';

export const Route = createFileRoute(
  '/dashboard/_authenticated/connect/$programId',
)({
  staticData: { workspace: dashboardViews.connectDetail },
  beforeLoad: capabilityGuard(dashboardViews.connectDetail),

  loader: ({ context, params, abortController }) =>
    prefetchDashboard(
      context,
      'connectDetail',
      { programId: params.programId },
      abortController.signal,
    ),

  pendingComponent: PagePending,
  component: ConnectDetailPage,
});
