import type { QueryClient } from '@tanstack/react-query';

import { createApi, type TransportOptions } from './client';
import type { WorkspaceModule } from './generated/data-contracts';
import { createQueryClient } from './query-client';
import { queryKeys } from './query-keys';

export function createApplicationServices(
  options: {
    queryClient?: QueryClient;
    getLocation?: TransportOptions['getLocation'];
    fetch?: typeof fetch;
  } = {},
) {
  const queryClient = options.queryClient ?? createQueryClient();

  let csrfToken = '';
  let identity = '';
  let permissions = '';
  let teamId = '';
  let moduleSignature: string | undefined;
  let redirecting = false;
  let generation = 0;
  let signedOut = false;
  let invalidationQueued = false;
  let invalidate: (() => void | Promise<void>) | undefined;

  const listeners = new Set<() => void>();
  const notifyIdentity = () => listeners.forEach((listener) => listener());

  const invalidateRouter = () => {
    if (invalidationQueued) return;

    invalidationQueued = true;
    queueMicrotask(() => {
      invalidationQueued = false;
      void invalidate?.();
    });
  };

  // Keep only capability metadata here; Query remains the sole data cache.
  queryClient.getQueryCache().subscribe((event) => {
    if (event.type !== 'updated' || event.action.type !== 'success') return;

    const { queryKey, state } = event.query;

    if (
      !teamId ||
      queryKey.length !== 3 ||
      queryKey[0] !== 'workspace' ||
      queryKey[1] !== teamId ||
      queryKey[2] !== 'modules' ||
      !Array.isArray(state.data)
    )
      return;

    const nextSignature = JSON.stringify(
      (state.data as WorkspaceModule[])
        .map((module) => [
          module.name,
          module.available,
          module.active,
          module.enabled,
          module.delegable,
          [...(module.missing_scopes ?? [])].sort(),
          [...(module.required_scopes ?? [])].sort(),
        ])
        .sort(([left], [right]) => String(left).localeCompare(String(right))),
    );
    const changed =
      moduleSignature !== undefined && moduleSignature !== nextSignature;
    moduleSignature = nextSignature;

    if (changed) invalidateRouter();
  });

  function clearSession() {
    generation += 1;
    csrfToken = '';
    permissions = '';
    teamId = '';
    moduleSignature = undefined;

    const changed = !!identity;
    identity = '';
    queryClient.clear();

    if (changed) notifyIdentity();

    if (!signedOut) {
      signedOut = true;
      invalidateRouter();
    }
  }

  // Logout leaves the page, so skip the router refresh and any 401 redirect
  // that would race the navigation to the login page.
  function signOut() {
    redirecting = true;
    signedOut = true;
    clearSession();
  }

  const api = createApi({
    ...options,
    getCsrfToken: () => csrfToken,
    getSessionGeneration: () => generation,
    onSession(session) {
      const nextIdentity = `${session.team_id}:${session.user_id}`;
      const nextPermissions = JSON.stringify([
        session.role,
        session.module_admin,
      ]);
      const identityChanged = !!identity && identity !== nextIdentity;
      const permissionsChanged =
        !!permissions && permissions !== nextPermissions;

      if (identityChanged || permissionsChanged) {
        moduleSignature = undefined;
        queryClient.removeQueries({
          predicate: (query) => query.queryKey[0] !== 'session',
        });
        queryClient.getMutationCache().clear();
      }

      const changed = identity !== nextIdentity;
      if (changed || permissionsChanged) generation += 1;

      identity = nextIdentity;
      teamId = session.team_id;
      permissions = nextPermissions;
      csrfToken =
        typeof session.csrf_token === 'string' ? session.csrf_token : '';
      redirecting = false;
      signedOut = false;

      // The transport has parsed the session, but the generated client still
      // needs to parse its own response. Publish before identity subscribers
      // can mount queries, so their workspace always matches this transport.
      queryClient.setQueryData(queryKeys.session, session);

      if (changed) notifyIdentity();
      if (identityChanged || permissionsChanged) invalidateRouter();
    },
    onUnauthorized() {
      clearSession();

      const browser =
        options.getLocation?.() ??
        (typeof location === 'undefined' ? undefined : location);

      if (
        !redirecting &&
        browser?.pathname.startsWith('/dashboard') &&
        browser.pathname !== '/dashboard/login'
      ) {
        redirecting = true;
        browser.assign(
          `/dashboard/login?next=${encodeURIComponent(browser.pathname + browser.search)}`,
        );
      }
    },
  });

  return {
    queryClient,
    api,
    clearSession,
    signOut,
    invalidateRouter,
    setRouterInvalidator(fn: () => void | Promise<void>) {
      invalidate = fn;
    },
    getIdentity: () => identity,
    getSessionGeneration: () => generation,
    isSignedOut: () => signedOut,
    subscribeIdentity(listener: () => void) {
      listeners.add(listener);

      return () => {
        listeners.delete(listener);
      };
    },
  };
}

export type ApplicationServices = ReturnType<typeof createApplicationServices>;
