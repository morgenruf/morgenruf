import { Analytics } from './generated/Analytics';
import { Automation } from './generated/Automation';
import { Connect } from './generated/Connect';
import { HttpClient } from './generated/http-client';
import { Insights } from './generated/Insights';
import { Kudos } from './generated/Kudos';
import { Mcp } from './generated/Mcp';
import { Members } from './generated/Members';
import { Public } from './generated/Public';
import { Reports } from './generated/Reports';
import { Session } from './generated/Session';
import { Standups } from './generated/Standups';
import { Webhooks } from './generated/Webhooks';
import { Workspace } from './generated/Workspace';
import { queryClient } from './query-client';

let csrfToken = '';
let redirecting = false;
let identity = '';

export function clearSession() {
  csrfToken = '';
  identity = '';
  queryClient.clear();
}

export const httpClient = new HttpClient({
  baseUrl: '',
  baseApiParams: { credentials: 'same-origin' },
  customFetch: async (input, init) => {
    const path =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.href
          : input.url;
    const requestUrl = new URL(path, location.origin);
    const privateApi =
      requestUrl.origin === location.origin &&
      requestUrl.pathname.startsWith('/dashboard/api/');

    const method = (init?.method ?? 'GET').toUpperCase();
    const headers = new Headers(init?.headers);

    if (privateApi && !['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken)
      headers.set('X-CSRF-Token', csrfToken);

    const response = await fetch(input, {
      ...init,
      headers,
      credentials: 'same-origin',
    });

    if (
      response.ok &&
      privateApi &&
      requestUrl.pathname === '/dashboard/api/me'
    ) {
      const session = await response.clone().json();
      const nextIdentity = `${session.team_id}:${session.user_id}`;

      if (identity && identity !== nextIdentity) {
        queryClient.removeQueries({
          predicate: (query) => query.queryKey[0] !== 'session',
        });
        queryClient.getMutationCache().clear();
      }

      identity = nextIdentity;
      csrfToken =
        typeof session.csrf_token === 'string' ? session.csrf_token : '';
    }

    if (response.status === 401 && privateApi) {
      clearSession();

      if (
        !redirecting &&
        location.pathname.startsWith('/dashboard') &&
        location.pathname !== '/dashboard/login'
      ) {
        redirecting = true;
        location.assign(
          `/dashboard/login?next=${encodeURIComponent(location.pathname + location.search)}`,
        );
      }
    }

    return response;
  },
});

export const api = {
  session: new Session(httpClient),
  standups: new Standups(httpClient),
  members: new Members(httpClient),
  reports: new Reports(httpClient),
  analytics: new Analytics(httpClient),
  workspace: new Workspace(httpClient),
  automation: new Automation(httpClient),
  webhooks: new Webhooks(httpClient),
  mcp: new Mcp(httpClient),
  connect: new Connect(httpClient),
  kudos: new Kudos(httpClient),
  insights: new Insights(httpClient),
  public: new Public(httpClient),
};
