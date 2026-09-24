import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import TodayPage from '@/modules/today/pages/today-page';

export const Route = createFileRoute('/dashboard/_authenticated/today')({
  staticData: { workspace: dashboardViews.today },
  beforeLoad: capabilityGuard(dashboardViews.today),

  loader: ({ context, abortController }) =>
    prefetchDashboard(context, 'today', {}, abortController.signal),

  pendingComponent: PagePending,
  component: TodayPage,
});
