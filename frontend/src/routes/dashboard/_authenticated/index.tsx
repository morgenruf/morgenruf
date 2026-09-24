import { createFileRoute, redirect } from '@tanstack/react-router';

import { legacyDashboardPath } from '@/common/lib/routes';

export const Route = createFileRoute('/dashboard/_authenticated/')({
  beforeLoad: ({ location }) => {
    throw redirect({ href: legacyDashboardPath(location.hash), replace: true });
  },
});
