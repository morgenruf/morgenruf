import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import KudosPage from '@/modules/kudos/pages/kudos-page';
import { validateSearch } from '@/modules/kudos/search';

export const Route = createFileRoute('/dashboard/_authenticated/kudos')({
  staticData: { workspace: dashboardViews.kudos },
  beforeLoad: capabilityGuard(dashboardViews.kudos),

  validateSearch,
  loaderDeps: ({ search }) => ({ days: search.days }),
  loader: ({ context, deps, abortController }) =>
    prefetchDashboard(context, 'kudos', deps, abortController.signal),

  pendingComponent: PagePending,
  component: KudosPage,
});
