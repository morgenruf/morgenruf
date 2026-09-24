import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import AnalyticsPage from '@/modules/analytics/pages/analytics-page';
import { validateSearch } from '@/modules/analytics/search';

export const Route = createFileRoute('/dashboard/_authenticated/analytics')({
  staticData: { workspace: dashboardViews.analytics },
  beforeLoad: capabilityGuard(dashboardViews.analytics),

  validateSearch,
  loaderDeps: ({ search }) => ({ days: search.days }),
  loader: ({ context, deps, abortController }) =>
    prefetchDashboard(context, 'analytics', deps, abortController.signal),

  pendingComponent: PagePending,
  component: AnalyticsPage,
});
