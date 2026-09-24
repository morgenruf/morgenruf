import { noop } from '@tanstack/react-query';
import { createFileRoute } from '@tanstack/react-router';

import { PagePending } from '@/app/startup-fallback';
import FeedPage from '@/modules/public/pages/feed-page';
import { publicFeedOptions } from '@/modules/public/queries';

export const Route = createFileRoute('/feed/$token')({
  loader: ({ context, params }) => {
    void context.services.queryClient
      .query(publicFeedOptions(context.services, params.token))
      .catch(noop);
  },

  pendingComponent: PagePending,
  component: FeedPage,
});
