import { createFileRoute } from '@tanstack/react-router';

import { dashboardViews } from '@/app/dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '@/app/route-loaders';
import { PagePending } from '@/app/startup-fallback';
import McpPage from '@/modules/mcp/pages/mcp-page';

export const Route = createFileRoute('/dashboard/_authenticated/mcp')({
  staticData: { workspace: dashboardViews.mcp },
  beforeLoad: capabilityGuard(dashboardViews.mcp),

  loader: ({ context, abortController }) =>
    prefetchDashboard(context, 'mcp', {}, abortController.signal),

  pendingComponent: PagePending,
  component: McpPage,
});
