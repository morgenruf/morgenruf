import { createRouter, type RouterHistory } from '@tanstack/react-router';

import { AppProviders } from '@/app/providers';
import { NotFound, RouteError } from '@/app/route-errors';
import { StartupFallback } from '@/app/startup-fallback';
import {
  createApplicationServices,
  type ApplicationServices,
} from '@/common/api/services';
import { parseSearch, stringifySearch } from '@/common/routing/search';

import { routeTree } from './routeTree.gen';

export function getRouter(
  options: { history?: RouterHistory; services?: ApplicationServices } = {},
) {
  const services = options.services ?? createApplicationServices();

  const router = createRouter({
    routeTree,
    context: { services },
    history: options.history,

    defaultPreload: 'intent',
    defaultPreloadStaleTime: 0,

    defaultPendingMs: 0,
    defaultPendingMinMs: 0,
    defaultPendingComponent: StartupFallback,
    defaultErrorComponent: RouteError,
    defaultNotFoundComponent: NotFound,

    notFoundMode: 'root',
    trailingSlash: 'preserve',
    parseSearch,
    stringifySearch,

    Wrap: ({ children }) => (
      <AppProviders services={services}>{children}</AppProviders>
    ),
  });

  services.setRouterInvalidator(() => router.invalidate());

  return router;
}

declare module '@tanstack/react-router' {
  interface Register {
    router: ReturnType<typeof getRouter>;
  }
}
