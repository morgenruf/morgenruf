import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import MembersPage from '@/modules/members/pages/members-page';
import { validateSearch } from '@/modules/members/search';

export const Route = createFileRoute('/dashboard/_authenticated/members')({
  staticData: { workspace: dashboardViews.members },
  beforeLoad: capabilityGuard(dashboardViews.members),

  validateSearch,
  loaderDeps: ({ search }) => ({ channel: search.channel }),
  loader: ({ context, deps, abortController }) =>
    prefetchDashboard(context, 'members', deps, abortController.signal),

  pendingComponent: PagePending,
  component: MembersPage,
});
