import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import WatercoolerPage from '@/modules/watercooler/pages/watercooler-page';

export const Route = createFileRoute('/dashboard/_authenticated/watercooler')({
  staticData: { workspace: dashboardViews.watercooler },
  beforeLoad: capabilityGuard(dashboardViews.watercooler),

  loader: ({ context, abortController }) =>
    prefetchDashboard(context, 'watercooler', {}, abortController.signal),

  pendingComponent: PagePending,
  component: WatercoolerPage,
});
