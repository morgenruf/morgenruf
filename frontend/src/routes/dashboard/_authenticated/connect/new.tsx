import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import { ConnectNewPage } from '@/modules/connect/pages';

export const Route = createFileRoute('/dashboard/_authenticated/connect/new')({
  staticData: { workspace: dashboardViews.connectNew },
  beforeLoad: capabilityGuard(dashboardViews.connectNew),

  loader: ({ context, abortController }) =>
    prefetchDashboard(context, 'connectNew', {}, abortController.signal),

  pendingComponent: PagePending,
  component: ConnectNewPage,
});
