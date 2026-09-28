import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import ProfilePage from '@/modules/profile/pages/profile-page';

export const Route = createFileRoute('/dashboard/_authenticated/profile')({
  staticData: { workspace: dashboardViews.profile },
  beforeLoad: capabilityGuard(dashboardViews.profile),

  loader: ({ context, abortController }) =>
    prefetchDashboard(context, 'profile', {}, abortController.signal),

  pendingComponent: PagePending,
  component: ProfilePage,
});
