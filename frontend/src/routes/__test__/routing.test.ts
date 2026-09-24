import { createMemoryHistory } from '@tanstack/react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createApplicationServices } from '@/common/api/services';
import { getRouter } from '@/router';

const session = {
  team_id: 'T1',
  user_id: 'U1',
  team_name: 'Workspace',
  role: 'admin',
  module_admin: [],
  csrf_token: 'private-csrf',
  mcp_endpoint: '/mcp',
};

const moduleNames = ['standup', 'connect', 'insights', 'kudos', 'mcp'];

function fixture(
  path: string,
  options: { signedOut?: boolean; unavailable?: string } = {},
) {
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const pathname = new URL(String(input), 'http://localhost').pathname;

    if (pathname === '/dashboard/api/me')
      return Response.json(
        options.signedOut ? { error: 'Unauthorized' } : session,
        { status: options.signedOut ? 401 : 200 },
      );

    if (pathname === '/dashboard/api/modules')
      return Response.json(
        moduleNames.map((name) => ({
          name,
          available: name !== options.unavailable,
          active: true,
          enabled: true,
          missing_scopes: [],
          required_scopes: [],
          delegable: true,
          nav: [],
        })),
      );

    return Response.json([]);
  });

  const services = createApplicationServices({
    fetch,
    getLocation: () => ({
      origin: 'http://localhost',
      pathname: new URL(path, 'http://localhost').pathname,
      search: '',
      assign: vi.fn(),
    }),
  });
  const router = getRouter({
    services,
    history: createMemoryHistory({ initialEntries: [path] }),
  });

  return { router, services, fetch };
}

afterEach(() => vi.restoreAllMocks());

describe('file route contracts', () => {
  it.each([
    '/dashboard/login',
    '/auth/result?status=success',
    '/email/result?result=subscribed',
    '/connect/zoom/result?status=connected',
    '/unknown',
    '/dashboard/unknown',
  ])('loads %s without bootstrapping a private session', async (path) => {
    const { router, fetch } = fixture(path);

    await router.load();

    expect(fetch).not.toHaveBeenCalled();
  });

  it('keeps public feed loading outside the authentication guard', async () => {
    const { router, fetch } = fixture('/feed/opaque-token');

    await router.load();

    expect(router.state.matches.at(-1)?.params).toMatchObject({
      token: 'opaque-token',
    });
    expect(fetch.mock.calls.map(([url]) => String(url))).toEqual([
      '/api/public/feed/opaque-token',
    ]);
  });

  it.each(['/dashboard/analytics', '/dashboard/analytics?days=oops'])(
    'validates direct-visit defaults for %s',
    async (path) => {
      const { router, services } = fixture(path);

      await router.load();

      expect(router.state.matches.at(-1)?.search).toMatchObject({
        days: 7,
        schedule: '',
        unenrolled: false,
      });
      expect(services.getIdentity()).toBe('T1:U1');
    },
  );

  it('preserves a decoded dynamic program parameter', async () => {
    const { router } = fixture('/dashboard/connect/42');

    await router.load();

    expect(router.state.matches.at(-1)?.params).toMatchObject({
      programId: '42',
    });
  });

  it.each(['/dashboard/#reports', '/dashboard/standups#reports'])(
    'retains the legacy report bookmark %s',
    async (path) => {
      const { router } = fixture(path);

      await router.load();

      expect(router.state.location.pathname).toBe('/dashboard/reports');
    },
  );

  it('redirects expired private sessions to public login', async () => {
    const { router } = fixture('/dashboard/standups', { signedOut: true });

    await router.load();

    expect(router.state.location.pathname).toBe('/dashboard/login');
  });

  it('does not prefetch page data for an unavailable capability', async () => {
    const { router, fetch } = fixture('/dashboard/kudos', {
      unavailable: 'kudos',
    });

    await router.load();

    expect(fetch.mock.calls.map(([url]) => String(url))).toEqual([
      '/dashboard/api/me',
      '/dashboard/api/modules',
    ]);
    expect(router.state.matches.at(-1)?.context).toMatchObject({
      capabilityAllowed: false,
    });
  });

  it('isolates application services for independent router instances', () => {
    const first = getRouter({ history: createMemoryHistory() });
    const second = getRouter({ history: createMemoryHistory() });

    expect(first.options.context.services).not.toBe(
      second.options.context.services,
    );
    expect(first.options.context.services.queryClient).not.toBe(
      second.options.context.services.queryClient,
    );

    first.options.context.services.queryClient.setQueryData(
      ['private'],
      'first-only',
    );

    expect(
      second.options.context.services.queryClient.getQueryData(['private']),
    ).toBeUndefined();
  });
});
