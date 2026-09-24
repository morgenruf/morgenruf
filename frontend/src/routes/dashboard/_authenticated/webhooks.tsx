import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import WebhooksPage from '@/modules/webhooks/pages/webhooks-page';

export const Route = createFileRoute('/dashboard/_authenticated/webhooks')({
  staticData: { workspace: dashboardViews.webhooks },
  beforeLoad: capabilityGuard(dashboardViews.webhooks),

  loader: ({ context, abortController }) =>
    prefetchDashboard(context, 'webhooks', {}, abortController.signal),

  pendingComponent: PagePending,
  component: WebhooksPage,
});
