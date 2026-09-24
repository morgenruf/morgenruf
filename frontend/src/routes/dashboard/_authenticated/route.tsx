import { createFileRoute, redirect } from '@tanstack/react-router';

import { DashboardLayout } from '@/app/dashboard-layout';
import { StartupFallback } from '@/app/startup-fallback';
import { sessionOptions } from '@/common/api/queries';
import {
  isLegacyDashboardHash,
  legacyDashboardPath,
} from '@/common/lib/routes';

export const Route = createFileRoute('/dashboard/_authenticated')({
  beforeLoad: async ({ context, location }) => {
    try {
      const session = await context.services.queryClient.fetchQuery(
        sessionOptions(context.services),
      );

      if (isLegacyDashboardHash(location.hash))
        throw redirect({
          href: legacyDashboardPath(location.hash),
          replace: true,
        });

      return { session };
    } catch (error) {
      if (
        context.services.isSignedOut() ||
        (error &&
          typeof error === 'object' &&
          'status' in error &&
          error.status === 401)
      )
        throw redirect({ to: '/dashboard/login', replace: true });

      throw error;
    }
  },

  pendingComponent: StartupFallback,
  component: DashboardLayout,
});
