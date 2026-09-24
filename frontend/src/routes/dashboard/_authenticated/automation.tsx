import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import AutomationPage from '@/modules/automation/pages/automation-page';

export const Route = createFileRoute('/dashboard/_authenticated/automation')({
  staticData: { workspace: dashboardViews.automation },
  beforeLoad: capabilityGuard(dashboardViews.automation),

  loader: ({ context, abortController }) =>
    prefetchDashboard(context, 'automation', {}, abortController.signal),

  pendingComponent: PagePending,
  component: AutomationPage,
});
