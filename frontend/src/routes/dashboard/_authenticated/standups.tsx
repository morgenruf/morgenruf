import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import { StandupsPage } from '@/modules/standups/pages';
import { validateSearch } from '@/modules/standups/search';

export const Route = createFileRoute('/dashboard/_authenticated/standups')({
  staticData: { workspace: dashboardViews.standups },
  beforeLoad: capabilityGuard(dashboardViews.standups),

  validateSearch,
  loader: ({ context, abortController }) =>
    prefetchDashboard(context, 'standups', {}, abortController.signal),

  pendingComponent: PagePending,
  component: StandupsPage,
});
