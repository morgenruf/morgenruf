import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { api, clearSession } from '../client';
import type { SessionInfo } from '../generated/data-contracts';
import { queryClient } from '../query-client';

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
  clearSession();
});

afterEach(() => {
  clearSession();
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
      vi.fn().mockResolvedValue(json({ error: 'Invalid feed' }, 404)),
    );

    await expect(
      api.public.getFeed({ token: 'revoked' }),
    ).rejects.toHaveProperty('status', 404);

    expect(queryClient.getQueryData(['workspace', 'T1', 'members'])).toEqual([
      'private',
    ]);
  });
});
