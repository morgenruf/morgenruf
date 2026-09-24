import { noop, QueryObserver } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';

import { deferred } from '@/test/deferred';

import {
  analyticsOptions,
  channelsOptions,
  memberDirectoryOptions,
  modulesOptions,
  sessionOptions,
  standupsOptions,
} from '../queries';
import { createApplicationServices } from '../services';

const instances: ReturnType<typeof createApplicationServices>[] = [];

function services(fetch: typeof globalThis.fetch) {
  const instance = createApplicationServices({ fetch });
  instances.push(instance);

  return instance;
}

afterEach(() =>
  instances.splice(0).forEach((instance) => instance.clearSession()),
);

it('shares a pending prefetch with component reads and reuses the fresh cache entry', async () => {
  const response = deferred<Response>();
  const fetch = vi.fn().mockReturnValue(response.promise);
  const instance = services(fetch);
  const options = standupsOptions(instance, 'T1');

  const prefetch = instance.queryClient.query(options).catch(noop);
  const observer = new QueryObserver(
    instance.queryClient,
    standupsOptions(instance, 'T1'),
  );
  const unsubscribe = observer.subscribe(() => {});

  expect(fetch).toHaveBeenCalledTimes(1);

  response.resolve(Response.json([{ id: 1, name: 'Daily' }]));
  await prefetch;

  expect(observer.getCurrentResult().data).toEqual([{ id: 1, name: 'Daily' }]);

  await instance.queryClient.query(standupsOptions(instance, 'T1')).catch(noop);

  expect(fetch).toHaveBeenCalledTimes(1);

  unsubscribe();
});

it('allows primary content to arrive while secondary queries are pending or fail', async () => {
  const secondary = deferred<Response>();
  const fetch = vi
    .fn()
    .mockImplementation((path: string) =>
      path.includes('/channels')
        ? secondary.promise
        : Promise.resolve(Response.json([{ id: 1 }])),
    );
  const instance = services(fetch);

  const pending = instance.queryClient
    .query(channelsOptions(instance, 'T1'))
    .catch(noop);
  await instance.queryClient.query(standupsOptions(instance, 'T1')).catch(noop);

  expect(
    instance.queryClient.getQueryData(standupsOptions(instance, 'T1').queryKey),
  ).toEqual([{ id: 1 }]);

  secondary.reject(new TypeError('Offline'));
  await pending;

  expect(
    instance.queryClient.getQueryState(channelsOptions(instance, 'T1').queryKey)
      ?.status,
  ).toBe('error');
  expect(
    instance.queryClient.getQueryData(standupsOptions(instance, 'T1').queryKey),
  ).toEqual([{ id: 1 }]);
});

it('uses the same analytics key across callers and preserves freshness policies', () => {
  const instance = services(vi.fn());

  expect(analyticsOptions(instance, 'T1', 14).queryKey).toEqual([
    'workspace',
    'T1',
    'analytics',
    14,
  ]);
  expect(memberDirectoryOptions(instance, 'T1').queryKey).toEqual([
    'workspace',
    'T1',
    'members',
    '',
  ]);
  expect(sessionOptions(instance).staleTime).toBe(60_000);
  expect(instance.queryClient.getDefaultOptions().queries).toMatchObject({
    staleTime: 30_000,
    retry: false,
  });
});

it('passes Query cancellation signals through the generated transport', async () => {
  let signal: AbortSignal | undefined;
  const instance = services(
    vi.fn().mockImplementation((_input, init) => {
      signal = init.signal;

      return new Promise((_resolve, reject) =>
        init.signal.addEventListener('abort', () =>
          reject(new DOMException('Aborted', 'AbortError')),
        ),
      );
    }),
  );
  const options = standupsOptions(instance, 'T1');

  const pending = instance.queryClient.query(options).catch(noop);
  await instance.queryClient.cancelQueries({ queryKey: options.queryKey });
  await pending;

  expect(signal?.aborted).toBe(true);
});

it('invalidates route capabilities only when a previously loaded module permission changes', async () => {
  const session = {
    team_id: 'T1',
    user_id: 'U1',
    role: 'admin',
    module_admin: [],
  };
  let modules = [
    {
      name: 'connect',
      available: true,
      active: true,
      missing_scopes: [] as string[],
    },
  ];
  const instance = services(
    vi
      .fn()
      .mockImplementation((path: string) =>
        Promise.resolve(
          Response.json(path.endsWith('/me') ? session : modules),
        ),
      ),
  );
  const invalidate = vi.fn();
  instance.setRouterInvalidator(invalidate);

  await instance.queryClient.fetchQuery(sessionOptions(instance));
  const options = modulesOptions(instance, 'T1');
  await instance.queryClient.fetchQuery(options);

  expect(invalidate).not.toHaveBeenCalled();

  await instance.queryClient.refetchQueries({ queryKey: options.queryKey });

  expect(invalidate).not.toHaveBeenCalled();

  modules = [{ ...modules[0], active: false, missing_scopes: ['im:write'] }];
  await instance.queryClient.refetchQueries({ queryKey: options.queryKey });

  expect(invalidate).toHaveBeenCalledTimes(1);

  await instance.queryClient.refetchQueries({ queryKey: options.queryKey });

  expect(invalidate).toHaveBeenCalledTimes(1);
});

it('resets module capability signatures across logout and identity changes', async () => {
  let session = {
    team_id: 'T1',
    user_id: 'U1',
    role: 'admin',
    module_admin: [],
  };
  let active = true;
  const instance = services(
    vi.fn().mockImplementation((path: string) =>
      Promise.resolve(
        Response.json(
          path.endsWith('/me')
            ? session
            : [
                {
                  name: 'connect',
                  available: true,
                  active,
                  missing_scopes: [],
                },
              ],
        ),
      ),
    ),
  );
  const invalidate = vi.fn();
  instance.setRouterInvalidator(invalidate);

  await instance.queryClient.fetchQuery(sessionOptions(instance));
  await instance.queryClient.fetchQuery(
    modulesOptions(instance, session.team_id),
  );

  instance.clearSession();
  await instance.queryClient.fetchQuery(sessionOptions(instance));
  active = false;
  invalidate.mockClear();

  await instance.queryClient.fetchQuery(
    modulesOptions(instance, session.team_id),
  );

  expect(invalidate).not.toHaveBeenCalled();

  session = { ...session, team_id: 'T2' };
  await instance.api.session.getSession();
  active = true;
  invalidate.mockClear();

  await instance.queryClient.fetchQuery(
    modulesOptions(instance, session.team_id),
  );

  expect(invalidate).not.toHaveBeenCalled();
});
