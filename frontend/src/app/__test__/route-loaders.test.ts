import { createMemoryHistory } from '@tanstack/react-router';
import { afterEach, expect, it, vi } from 'vitest';

import type { SessionInfo } from '@/common/api/generated/data-contracts';
import { modulesOptions, sessionOptions } from '@/common/api/queries';
import { createApplicationServices } from '@/common/api/services';
import { connectProgramsOptions } from '@/modules/connect/queries';
import { getRouter } from '@/router';
import { deferred } from '@/test/deferred';

import { dashboardViews } from '../dashboard-routes';
import { capabilityGuard, prefetchDashboard } from '../route-loaders';
import type { AuthenticatedContext } from '../router-context';

const session: SessionInfo = {
  team_id: 'T1',
  user_id: 'U1',
  team_name: 'Team',
  role: 'admin',
  module_admin: [],
  csrf_token: 'csrf',
  mcp_endpoint: '/mcp',
};

const available = {
  name: 'connect',
  available: true,
  active: true,
  missing_scopes: [],
};

const instances: ReturnType<typeof createApplicationServices>[] = [];

function create(fetch: typeof globalThis.fetch) {
  const services = createApplicationServices({ fetch });

  instances.push(services);

  return services;
}

afterEach(() => {
  for (const services of instances.splice(0)) {
    services.setRouterInvalidator(() => {});
    services.clearSession();
  }
});

it('awaits authentication and capabilities before starting route data without awaiting page queries', async () => {
  const me = deferred<Response>();
  const modules = deferred<Response>();
  const programs = deferred<Response>();
  const fetch = vi.fn().mockImplementation((path: string) => {
    if (path.endsWith('/me')) return me.promise;
    if (path.endsWith('/modules')) return modules.promise;
    if (path.endsWith('/programs')) return programs.promise;

    return Promise.resolve(Response.json([]));
  });
  const services = create(fetch);
  const router = getRouter({
    services,
    history: createMemoryHistory({ initialEntries: ['/dashboard/connect'] }),
  });
  const loading = router.load();

  await vi.waitFor(() =>
    expect(fetch.mock.calls.map(([path]) => path)).toEqual([
      '/dashboard/api/me',
    ]),
  );

  me.resolve(Response.json(session));

  await vi.waitFor(() =>
    expect(fetch.mock.calls.map(([path]) => path)).toEqual([
      '/dashboard/api/me',
      '/dashboard/api/modules',
    ]),
  );

  modules.resolve(Response.json([available]));
  await loading;

  expect(
    router.state.matches.every((match) => match.status === 'success'),
  ).toBe(true);
  expect(
    services.queryClient.getQueryState(
      connectProgramsOptions(services, 'T1').queryKey,
    )?.fetchStatus,
  ).toBe('fetching');
  expect(
    fetch.mock.calls.some(
      ([path]) => path === '/dashboard/api/connect/programs',
    ),
  ).toBe(true);

  programs.resolve(Response.json([]));
});

it.each([
  ['unavailable', { available: false }],
  ['disabled', { active: false }],
  ['missing scopes', { missing_scopes: ['im:write'] }],
])('does not prefetch an %s capability', async (_name, override) => {
  const fetch = vi
    .fn()
    .mockImplementation((path: string) =>
      Promise.resolve(
        Response.json(
          path.endsWith('/me') ? session : [{ ...available, ...override }],
        ),
      ),
    );
  const services = create(fetch);
  const current = await services.queryClient.fetchQuery(
    sessionOptions(services),
  );
  const context: AuthenticatedContext = { services, session: current };
  const result = await capabilityGuard(dashboardViews.connect)({
    context,
    abortController: new AbortController(),
  });

  prefetchDashboard({ ...context, ...result }, 'connect');

  expect(result.capabilityAllowed).toBe(false);
  expect(fetch.mock.calls.map(([path]) => path)).toEqual([
    '/dashboard/api/me',
    '/dashboard/api/modules',
  ]);
});

it('preserves administration checks and refreshes capabilities after module invalidation', async () => {
  let active = false;
  const member = { ...session, role: 'member' as const };
  const fetch = vi
    .fn()
    .mockImplementation((path: string) =>
      Promise.resolve(
        Response.json(
          path.endsWith('/me') ? member : [{ ...available, active }],
        ),
      ),
    );
  const services = create(fetch);
  const current = await services.queryClient.fetchQuery(
    sessionOptions(services),
  );
  const context: AuthenticatedContext = { services, session: current };
  const options = { context, abortController: new AbortController() };

  expect(
    (await capabilityGuard(dashboardViews.connect)(options)).capabilityAllowed,
  ).toBe(false);

  active = true;
  await services.queryClient.invalidateQueries({
    queryKey: modulesOptions(services, 'T1').queryKey,
  });

  expect(
    (await capabilityGuard(dashboardViews.connect)(options)).capabilityAllowed,
  ).toBe(true);
  expect(
    (await capabilityGuard(dashboardViews.connectNew)(options))
      .capabilityAllowed,
  ).toBe(false);

  prefetchDashboard({ ...context, capabilityAllowed: false }, 'connectNew');

  expect(
    fetch.mock.calls.some(
      ([path]) => path.endsWith('/channels') || path.endsWith('/zoom'),
    ),
  ).toBe(false);
});

it.each(['navigation', 'identity'] as const)(
  'stops cached dependent prefetch after a %s change',
  async (change) => {
    const fetch = vi.fn().mockResolvedValue(Response.json(session));
    const services = create(fetch);
    const current = await services.queryClient.fetchQuery(
      sessionOptions(services),
    );
    const context: AuthenticatedContext = { services, session: current };

    services.queryClient.setQueryData(
      ['workspace', 'T1', 'connect', 'programs'],
      [{ id: 7 }],
    );

    const abort = new AbortController();

    prefetchDashboard(context, 'connectAttendance', {}, abort.signal);

    if (change === 'navigation') abort.abort();
    else services.clearSession();

    await new Promise<void>((resolve) => queueMicrotask(resolve));

    expect(fetch).toHaveBeenCalledTimes(1);
  },
);

it('rejects stale permission context while capability checks are pending', async () => {
  let currentSession = session;
  const modules = deferred<Response>();
  const fetch = vi
    .fn()
    .mockImplementation((path: string) =>
      path.endsWith('/me')
        ? Promise.resolve(Response.json(currentSession))
        : modules.promise,
    );
  const services = create(fetch);
  const current = await services.queryClient.fetchQuery(
    sessionOptions(services),
  );
  const context: AuthenticatedContext = { services, session: current };
  const allowed = capabilityGuard(dashboardViews.connectNew)({
    context,
    abortController: new AbortController(),
  });

  currentSession = { ...session, role: 'member' };
  await services.api.session.getSession();
  modules.resolve(Response.json([available]));

  expect((await allowed).capabilityAllowed).toBe(false);

  prefetchDashboard({ ...context, capabilityAllowed: false }, 'connectNew');

  expect(
    fetch.mock.calls.some(
      ([path]) => path.endsWith('/channels') || path.endsWith('/zoom'),
    ),
  ).toBe(false);
});

it('keeps detail-only resources and dialog requests gated by their existing conditions', async () => {
  const fetch = vi
    .fn()
    .mockImplementation((path: string) =>
      Promise.resolve(Response.json(path.endsWith('/me') ? session : [])),
    );
  const services = create(fetch);
  const current = await services.queryClient.fetchQuery(
    sessionOptions(services),
  );
  const context: AuthenticatedContext = { services, session: current };

  services.queryClient.setQueryData(
    ['workspace', 'T1', 'connect', 'programs'],
    [{ id: 7 }],
  );

  prefetchDashboard(context, 'connectDetail', { programId: '404' });
  await new Promise<void>((resolve) => queueMicrotask(resolve));

  expect(fetch).toHaveBeenCalledTimes(1);

  prefetchDashboard(context, 'connectDetail', { programId: '7' });

  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));

  expect(fetch.mock.calls.map(([path]) => path)).toEqual([
    '/dashboard/api/me',
    '/dashboard/api/channels',
    '/dashboard/api/connect/zoom',
  ]);
});

it('redirects an expired session without starting page data or repeating bootstrap forever', async () => {
  const fetch = vi
    .fn()
    .mockImplementation(() =>
      Promise.resolve(Response.json({ error: 'Expired' }, { status: 401 })),
    );
  const services = create(fetch);
  const router = getRouter({
    services,
    history: createMemoryHistory({ initialEntries: ['/dashboard/members'] }),
  });

  await router.load();
  await vi.waitFor(() =>
    expect(router.state.location.pathname).toBe('/dashboard/login'),
  );

  expect(fetch.mock.calls.every(([path]) => path === '/dashboard/api/me')).toBe(
    true,
  );
  expect(fetch.mock.calls.length).toBeLessThanOrEqual(2);
  expect(services.queryClient.getQueryCache().getAll()).toHaveLength(0);
});

it('never starts capability requests from an old workspace context', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(Response.json(session))
    .mockResolvedValueOnce(Response.json({ ...session, team_id: 'T2' }));
  const services = create(fetch);
  const old = await services.api.session.getSession();

  await services.api.session.getSession();

  const result = await capabilityGuard(dashboardViews.connect)({
    context: { services, session: old.data },
    abortController: new AbortController(),
  });

  expect(result.capabilityAllowed).toBe(false);
  expect(fetch).toHaveBeenCalledTimes(2);
});
