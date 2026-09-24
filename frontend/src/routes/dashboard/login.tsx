import { createFileRoute } from '@tanstack/react-router';

import { PagePending } from '@/app/startup-fallback';
import LoginPage from '@/modules/auth/pages/login-page';
import { validateSearch } from '@/modules/auth/search';

export const Route = createFileRoute('/dashboard/login')({
  validateSearch,

  pendingComponent: PagePending,
  component: LoginPage,
});
