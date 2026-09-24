import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import { SettingsPage } from '@/modules/settings/pages';

export const Route = createFileRoute('/dashboard/_authenticated/settings')({
  staticData: { workspace: dashboardViews.settings },
  beforeLoad: capabilityGuard(dashboardViews.settings),

  loader: ({ context, abortController }) =>
    prefetchDashboard(context, 'settings', {}, abortController.signal),

  pendingComponent: PagePending,
  component: SettingsPage,
});
