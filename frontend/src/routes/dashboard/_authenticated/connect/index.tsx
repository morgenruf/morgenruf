import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import { ConnectListPage } from '@/modules/connect/pages';

export const Route = createFileRoute('/dashboard/_authenticated/connect/')({
  staticData: { workspace: dashboardViews.connect },
  beforeLoad: capabilityGuard(dashboardViews.connect),

  loader: ({ context, abortController }) =>
    prefetchDashboard(context, 'connect', {}, abortController.signal),

  pendingComponent: PagePending,
  component: ConnectListPage,
});
