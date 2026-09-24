import { useContext, useState, type ReactNode } from 'react';
import { QueryClientContext, QueryClientProvider } from '@tanstack/react-query';
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
  type AnyRoute,
} from '@tanstack/react-router';

import { createApplicationServices } from '@/common/api/services';
import { ServicesProvider } from '@/common/api/services-context';
import { parseSearch, stringifySearch } from '@/common/routing/search';
import { validateSearch as analytics } from '@/modules/analytics/search';
import { validateSearch as auth } from '@/modules/auth/search';
import { validateSearch as connect } from '@/modules/connect/search';
import { validateSearch as kudos } from '@/modules/kudos/search';
import { validateSearch as members } from '@/modules/members/search';
import { validateSearch as publicSearch } from '@/modules/public/search';
import { validateSearch as reports } from '@/modules/reports/search';
import { validateSearch as standups } from '@/modules/standups/search';

const schemas = {
  analytics,
  login: auth,
  attendance: connect,
  kudos,
  members,
  reports,
  standups,
  result: publicSearch,
};

type TestRouterOptions = {
  routeId: string;
  children: ReactNode;
  initialEntries?: string[];
};

/** An isolated route with production route IDs and URL validation, without auth loaders. */
export function createTestRouter({
  routeId,
  children,
  initialEntries,
}: TestRouterOptions) {
  const root = createRootRoute({ component: Outlet });
  const segments = routeId.split('/').filter(Boolean);
  let parent: AnyRoute = root;
  const routes: AnyRoute[] = [root];

  for (const [index, segment] of segments.entries()) {
    const leaf = index === segments.length - 1;
    const ancestor = parent;
    const schema = schemas[segment as keyof typeof schemas];
    const route = createRoute({
      getParentRoute: () => ancestor,
      ...(segment.startsWith('_') ? { id: segment } : { path: segment }),
      component: leaf ? () => children : Outlet,
      ...(leaf && schema
        ? {
            validateSearch: (value: Record<string, unknown>) =>
              schema.parse(value),
          }
        : {}),
    });

    routes.push(route);
    parent = route;
  }

  for (let index = routes.length - 2; index >= 0; index--)
    routes[index].addChildren([routes[index + 1]]);

  return createRouter({
    routeTree: root,
    history: createMemoryHistory({
      initialEntries: initialEntries ?? [
        routeId.replace('/_authenticated', ''),
      ],
    }),
    parseSearch,
    stringifySearch,
    defaultPendingMinMs: 0,
    defaultPendingMs: 0,
  });
}

export function TestRouter(options: TestRouterOptions) {
  const queryClient = useContext(QueryClientContext);
  const [services] = useState(() => createApplicationServices({ queryClient }));
  const [router] = useState(() => createTestRouter(options));

  return (
    <ServicesProvider services={services}>
      <QueryClientProvider client={services.queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ServicesProvider>
  );
}
