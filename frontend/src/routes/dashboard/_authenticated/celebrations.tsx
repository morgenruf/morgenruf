import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import CelebrationsPage from '@/modules/celebrations/pages/celebrations-page';

export const Route = createFileRoute('/dashboard/_authenticated/celebrations')({
  staticData: { workspace: dashboardViews.celebrations },
  beforeLoad: capabilityGuard(dashboardViews.celebrations),

  loader: ({ context, abortController }) =>
    prefetchDashboard(context, 'celebrations', {}, abortController.signal),

  pendingComponent: PagePending,
  component: CelebrationsPage,
});
