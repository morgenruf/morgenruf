import { createFileRoute } from '@tanstack/react-router';

import { PagePending } from '@/app/startup-fallback';
import ResultPage from '@/modules/public/pages/result-page';
import { validateSearch } from '@/modules/public/search';

export const Route = createFileRoute('/connect/zoom/result')({
  validateSearch,

  pendingComponent: PagePending,
  component: ResultPage,
});
