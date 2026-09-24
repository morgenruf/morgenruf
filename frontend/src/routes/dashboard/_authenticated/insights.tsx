import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import InsightsPage from '@/modules/insights/pages/insights-page';

export const Route = createFileRoute('/dashboard/_authenticated/insights')({
  staticData: { workspace: dashboardViews.insights },
  beforeLoad: capabilityGuard(dashboardViews.insights),

  loader: ({ context, abortController }) =>
    prefetchDashboard(context, 'insights', {}, abortController.signal),

  pendingComponent: PagePending,
  component: InsightsPage,
});
