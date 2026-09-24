import { createMemoryHistory, RouterProvider } from '@tanstack/react-router';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';

import type { RouterContext } from '@/app/router-context';
import { createApplicationServices } from '@/common/api/services';
import { getRouter } from '@/router';
import { mockViewport } from '@/test/match-media';

// Exercise the actual route tree and loaders in a normal test container.
vi.mock('@/routes/__root', async () => {
  const { createRootRouteWithContext, Outlet } =
    await import('@tanstack/react-router');
  const { RouteError } = await import('@/app/route-errors');

  return {
    Route: createRootRouteWithContext<RouterContext>()({
      component: Outlet,
      errorComponent: RouteError,
    }),
  };
});

afterEach(() => vi.unstubAllGlobals());

it('retries failed initial session bootstrap and renders the requested page', async () => {
  mockViewport();

  let sessionRequests = 0;
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    if (String(input) === '/dashboard/api/me') {
      sessionRequests++;

      if (sessionRequests === 1)
        return Response.json(
          { error: 'Temporarily unavailable' },
          { status: 500 },
        );

      return Response.json({
        team_id: 'T1',
        user_id: 'U1',
        team_name: 'Recovered workspace',
        role: 'admin',
        module_admin: [],
        csrf_token: 'csrf',
        mcp_endpoint: '/mcp',
      });
    }

    return Response.json([]);
  });
  const services = createApplicationServices({ fetch });
  const router = getRouter({
    services,
    history: createMemoryHistory({ initialEntries: ['/dashboard/members'] }),
  });

  render(<RouterProvider router={router} />);

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Temporarily unavailable',
  );
  expect(sessionRequests).toBe(1);

  await userEvent.click(screen.getByRole('button', { name: 'Try again' }));

  expect(await screen.findByRole('heading', { name: 'Members' })).toBeVisible();
  expect(
    screen.getByRole('navigation', { name: 'Main navigation' }),
  ).toBeVisible();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(sessionRequests).toBe(2);
  expect(router.state.location.pathname).toBe('/dashboard/members');
});
