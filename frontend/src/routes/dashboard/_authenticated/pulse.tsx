import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import PulsePage from '@/modules/pulse/pages/pulse-page';

export const Route = createFileRoute('/dashboard/_authenticated/pulse')({
  staticData: { workspace: dashboardViews.pulse },
  beforeLoad: capabilityGuard(dashboardViews.pulse),

  loader: ({ context, abortController }) =>
    prefetchDashboard(context, 'pulse', {}, abortController.signal),

  pendingComponent: PagePending,
  component: PulsePage,
});
