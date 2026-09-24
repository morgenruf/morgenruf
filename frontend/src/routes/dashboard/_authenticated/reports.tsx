import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import ReportsPage from '@/modules/reports/pages/reports-page';
import { validateSearch } from '@/modules/reports/search';

export const Route = createFileRoute('/dashboard/_authenticated/reports')({
  staticData: { workspace: dashboardViews.reports },
  beforeLoad: capabilityGuard(dashboardViews.reports),

  validateSearch,
  loaderDeps: ({ search }) => ({
    date_from: search.date_from,
    date_to: search.date_to,
    user_id: search.user_id,
  }),
  loader: ({ context, deps, abortController }) =>
    prefetchDashboard(context, 'reports', deps, abortController.signal),

  pendingComponent: PagePending,
  component: ReportsPage,
});
