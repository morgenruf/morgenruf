import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test/deferred';

import type { SessionInfo } from '../generated/data-contracts';
import { memberDirectoryOptions, sessionOptions } from '../queries';
import { queryKeys } from '../query-keys';
import { createApplicationServices } from '../services';

let services: ReturnType<typeof createApplicationServices>;
let api: ReturnType<typeof createApplicationServices>['api'];
let queryClient: ReturnType<typeof createApplicationServices>['queryClient'];

const session = (team_id = 'T1'): SessionInfo => ({
  team_id,
  team_name: 'Team',
  user_id: 'U1',
  role: 'admin',
  module_admin: [],
  mcp_endpoint: 'https://example.test/mcp',
  csrf_token: 'csrf-value',
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });

beforeEach(() => {
  services = createApplicationServices();
  ({ api, queryClient } = services);
});

afterEach(() => {
  services.clearSession();
  vi.unstubAllGlobals();
});

describe('generated client transport', () => {
  it('uses same-origin cookies and adds bootstrap CSRF only to mutations', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(session()))
      .mockResolvedValueOnce(json([]))
      .mockResolvedValueOnce(json({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    await api.session.getSession();
    await api.members.listMembers();
    await api.session.logout();

    expect(fetchMock.mock.calls[0][1].credentials).toBe('same-origin');
    expect(
      new Headers(fetchMock.mock.calls[1][1].headers).has('X-CSRF-Token'),
    ).toBe(false);
    expect(
      new Headers(fetchMock.mock.calls[2][1].headers).get('X-CSRF-Token'),
    ).toBe('csrf-value');
  });

  it('removes data from the previous identity when bootstrap switches workspace', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(json(session('T1')))
        .mockResolvedValueOnce(json(session('T2'))),
    );

    await api.session.getSession();
    queryClient.setQueryData(['workspace', 'T1', 'members'], ['private']);

    await api.session.getSession();

    expect(
      queryClient.getQueryData(['workspace', 'T1', 'members']),
    ).toBeUndefined();
  });

  it('drops one-time mutation results when the signed-in identity changes', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(json(session('T1')))
        .mockResolvedValueOnce(json(session('T2'))),
    );

    await api.session.getSession();

    const mutation = queryClient.getMutationCache().build(queryClient, {
      mutationFn: async () => ({ key: 'one-time-secret' }),
      gcTime: Infinity,
    });

    await mutation.execute(undefined);

    expect(queryClient.getMutationCache().getAll()).toHaveLength(1);

    await api.session.getSession();

    expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
  });

  it('does not attach browser CSRF to an overridden external API origin', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(session()))
      .mockResolvedValueOnce(json({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    await api.session.getSession();
    await api.session.logout({ baseUrl: 'https://external.example' });

    expect(
      new Headers(fetchMock.mock.calls[1][1].headers).has('X-CSRF-Token'),
    ).toBe(false);
  });

  it('clears cached workspace data when an authenticated request expires', async () => {
    queryClient.setQueryData(['workspace', 'T1', 'members'], ['private']);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(json({ error: 'Not authenticated' }, 401)),
    );

    await expect(api.members.listMembers()).rejects.toHaveProperty(
      'status',
      401,
    );

    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  });

  it('keeps public feed failures independent of an existing dashboard session', async () => {
    queryClient.setQueryData(['workspace', 'T1', 'members'], ['private']);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(json({ error: 'Invalid feed' }, 401)),
    );

    await expect(
      api.public.getFeed({ token: 'revoked' }),
    ).rejects.toHaveProperty('status', 401);

    expect(queryClient.getQueryData(['workspace', 'T1', 'members'])).toEqual([
      'private',
    ]);
  });
});

it('keeps CSRF and cache state isolated between application instances', async () => {
  const firstFetch = vi
    .fn()
    .mockResolvedValueOnce(json(session()))
    .mockResolvedValueOnce(json({ ok: true }));
  const secondFetch = vi.fn().mockResolvedValue(json({ ok: true }));
  const first = createApplicationServices({ fetch: firstFetch });
  const second = createApplicationServices({ fetch: secondFetch });

  await first.api.session.getSession();
  first.queryClient.setQueryData(['workspace', 'T1', 'members'], ['private']);
  await first.api.session.logout();
  await second.api.session.logout();

  expect(
    new Headers(firstFetch.mock.calls[1][1].headers).get('X-CSRF-Token'),
  ).toBe('csrf-value');
  expect(
    new Headers(secondFetch.mock.calls[0][1].headers).has('X-CSRF-Token'),
  ).toBe(false);
  expect(second.queryClient.getQueryCache().getAll()).toHaveLength(0);

  second.clearSession();

  expect(
    first.queryClient.getQueryData(['workspace', 'T1', 'members']),
  ).toEqual(['private']);

  first.clearSession();
});

it('redirects only once for concurrent private unauthorized responses', async () => {
  const assign = vi.fn();
  const instance = createApplicationServices({
    getLocation: () => ({
      origin: 'https://morgenruf.test',
      pathname: '/dashboard/members',
      search: '?channel=C1',
      assign,
    }),
    fetch: vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(json({ error: 'Expired' }, 401)),
      ),
  });

  await Promise.allSettled([
    instance.api.members.listMembers(),
    instance.api.workspace.listModules(),
  ]);

  expect(assign).toHaveBeenCalledExactlyOnceWith(
    '/dashboard/login?next=%2Fdashboard%2Fmembers%3Fchannel%3DC1',
  );
});

it('notifies identity subscribers and router guards when identity or privileges change', async () => {
  const invalidate = vi.fn();
  const changed = vi.fn();
  const instance = createApplicationServices({
    fetch: vi
      .fn()
      .mockResolvedValueOnce(json(session()))
      .mockResolvedValueOnce(json({ ...session(), role: 'member' }))
      .mockResolvedValueOnce(json(session('T2'))),
  });
  instance.setRouterInvalidator(invalidate);
  const unsubscribe = instance.subscribeIdentity(changed);

  await instance.api.session.getSession();

  expect(instance.getIdentity()).toBe('T1:U1');
  expect(invalidate).not.toHaveBeenCalled();

  await instance.api.session.getSession();

  expect(invalidate).toHaveBeenCalledTimes(1);

  await instance.api.session.getSession();

  expect(instance.getIdentity()).toBe('T2:U1');
  expect(changed).toHaveBeenCalledTimes(2);
  expect(invalidate).toHaveBeenCalledTimes(2);

  instance.clearSession();

  expect(instance.getIdentity()).toBe('');

  unsubscribe();
});

it('discards a delayed session response after logout instead of restoring CSRF or identity', async () => {
  let finish!: (response: Response) => void;
  const fetch = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValue(json({ ok: true }));
  const instance = createApplicationServices({ fetch });

  const pending = instance.api.session.getSession();
  instance.clearSession();
  finish(json(session()));

  await expect(pending).rejects.toHaveProperty('name', 'AbortError');
  expect(instance.getIdentity()).toBe('');

  await instance.api.session.logout();

  expect(new Headers(fetch.mock.calls[1][1].headers).has('X-CSRF-Token')).toBe(
    false,
  );
});

it('discards private mutation results from a previous identity', async () => {
  let finish!: (response: Response) => void;
  const instance = createApplicationServices({
    fetch: vi
      .fn()
      .mockResolvedValueOnce(json(session()))
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve;
          }),
      )
      .mockResolvedValueOnce(json(session('T2'))),
  });

  await instance.api.session.getSession();
  const pending = instance.api.mcp.createKey({ name: 'Example' });
  await instance.api.session.getSession();
  finish(json({ key: 'one-time-secret' }));

  await expect(pending).rejects.toHaveProperty('name', 'AbortError');
  expect(instance.getIdentity()).toBe('T2:U1');

  instance.clearSession();
});

it('discards a mutation even if logout happens during generated response parsing', async () => {
  const instance = createApplicationServices({
    fetch: vi
      .fn()
      .mockResolvedValueOnce(json(session()))
      .mockImplementationOnce(() => {
        const response = json({ key: 'one-time-secret' });
        const clone = response.clone.bind(response);

        response.clone = () => {
          const copy = clone();
          const parse = copy.json.bind(copy);

          copy.json = async () => {
            const data = await parse();
            instance.clearSession();

            return data;
          };

          return copy;
        };

        return Promise.resolve(response);
      }),
  });

  await instance.api.session.getSession();
  await expect(
    instance.api.mcp.createKey({ name: 'Example' }),
  ).rejects.toHaveProperty('name', 'AbortError');
  expect(instance.getIdentity()).toBe('');
});

it('deduplicates unauthorized router invalidation instead of creating a refetch loop', async () => {
  const instance = createApplicationServices({
    fetch: vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(json({ error: 'Expired' }, 401)),
      ),
  });
  const invalidate = vi.fn(() => {
    void instance.api.session.getSession().catch(() => {});
  });
  instance.setRouterInvalidator(invalidate);

  await expect(instance.api.session.getSession()).rejects.toHaveProperty(
    'status',
    401,
  );
  await vi.waitFor(() => expect(invalidate).toHaveBeenCalledTimes(1));

  await expect(instance.api.session.getSession()).rejects.toHaveProperty(
    'status',
    401,
  );
  expect(invalidate).toHaveBeenCalledTimes(1);
});

it('publishes the new cached session before identity subscribers can start workspace queries', async () => {
  const parsing = deferred<void>();
  const parsed = deferred<SessionInfo>();
  const nextSession = session('T2');
  const response = json(nextSession);
  const clone = response.clone.bind(response);
  let clones = 0;

  response.clone = () => {
    const copy = clone();

    if (++clones === 2) {
      copy.json = () => {
        parsing.resolve();

        return parsed.promise;
      };
    }

    return copy;
  };

  const instance = createApplicationServices({
    fetch: vi
      .fn()
      .mockResolvedValueOnce(json(session('T1')))
      .mockResolvedValueOnce(response)
      .mockResolvedValueOnce(json([{ id: 'U2', name: 'Private T2' }])),
  });

  await instance.queryClient.fetchQuery(sessionOptions(instance));
  instance.queryClient.setQueryData(
    ['workspace', 'T1', 'members', ''],
    [{ id: 'U1', name: 'Private T1' }],
  );

  const seen: Array<{ identity: string; cachedTeam: string | undefined }> = [];
  const unsubscribe = instance.subscribeIdentity(() => {
    seen.push({
      identity: instance.getIdentity(),
      cachedTeam: instance.queryClient.getQueryData<SessionInfo>(
        queryKeys.session,
      )?.team_id,
    });
  });

  const pending = instance.queryClient.fetchQuery({
    ...sessionOptions(instance),
    staleTime: 0,
  });
  await parsing.promise;

  expect(seen).toEqual([{ identity: 'T2:U1', cachedTeam: 'T2' }]);

  const cachedSession = instance.queryClient.getQueryData<SessionInfo>(
    queryKeys.session,
  )!;
  await instance.queryClient.fetchQuery(
    memberDirectoryOptions(instance, cachedSession.team_id),
  );
  parsed.resolve(nextSession);
  await pending;

  expect(
    instance.queryClient.getQueryData(['workspace', 'T1', 'members', '']),
  ).toBeUndefined();
  expect(
    instance.queryClient.getQueryData(['workspace', 'T2', 'members', '']),
  ).toEqual([{ id: 'U2', name: 'Private T2' }]);

  unsubscribe();
  instance.clearSession();
});
