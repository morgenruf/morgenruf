import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import PollsPage from '@/modules/polls/pages/polls-page';

export const Route = createFileRoute('/dashboard/_authenticated/polls')({
  staticData: { workspace: dashboardViews.polls },
  beforeLoad: capabilityGuard(dashboardViews.polls),

  loader: ({ context, abortController }) =>
    prefetchDashboard(context, 'polls', {}, abortController.signal),

  pendingComponent: PagePending,
  component: PollsPage,
});
