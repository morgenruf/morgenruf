import { Analytics } from './generated/Analytics';
import { Automation } from './generated/Automation';
import { Connect } from './generated/Connect';
import type { SessionInfo } from './generated/data-contracts';
import { HttpClient, type FullRequestParams } from './generated/http-client';
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

export interface TransportOptions {
  getCsrfToken: () => string;
  getSessionGeneration: () => number;
  onSession: (session: SessionInfo) => void;
  onUnauthorized: () => void;
  getLocation?: () =>
    Pick<Location, 'origin' | 'pathname' | 'search' | 'assign'> | undefined;
  fetch?: typeof fetch;
}

/** Each application owns its transport and authentication state. */
export function createApi(options: TransportOptions) {
  const responseGenerations = new WeakMap<Response, number>();
  const expiredRequest = () =>
    new DOMException('The authentication session changed.', 'AbortError');

  const httpClient = new HttpClient({
    baseUrl: '',
    baseApiParams: { credentials: 'same-origin' },
    customFetch: async (input, init) => {
      const browser =
        options.getLocation?.() ??
        (typeof location === 'undefined' ? undefined : location);
      const path =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const requestUrl = new URL(path, browser?.origin ?? 'http://localhost');
      const privateApi =
        requestUrl.origin === (browser?.origin ?? 'http://localhost') &&
        requestUrl.pathname.startsWith('/dashboard/api/');
      const generation = options.getSessionGeneration();

      const headers = new Headers(init?.headers);
      const method = (init?.method ?? 'GET').toUpperCase();
      const csrfToken = options.getCsrfToken();

      if (
        privateApi &&
        !['GET', 'HEAD', 'OPTIONS'].includes(method) &&
        csrfToken
      )
        headers.set('X-CSRF-Token', csrfToken);

      const response = await (options.fetch ?? fetch)(input, {
        ...init,
        headers,
        credentials: 'same-origin',
      });

      if (privateApi) {
        if (generation !== options.getSessionGeneration())
          throw expiredRequest();

        if (response.ok && requestUrl.pathname === '/dashboard/api/me') {
          const session = await response.clone().json();

          if (generation !== options.getSessionGeneration())
            throw expiredRequest();

          options.onSession(session);
        }

        if (response.status === 401) options.onUnauthorized();
        responseGenerations.set(response, options.getSessionGeneration());
      }

      return response;
    },
  });

  // Generated clients parse their response after customFetch returns. Check again
  // after parsing so a late mutation cannot deliver a secret into a new session.
  const request = httpClient.request;
  httpClient.request = async <T, E>(params: FullRequestParams) => {
    const response = await request<T, E>(params);
    const generation = responseGenerations.get(response);

    if (
      generation !== undefined &&
      generation !== options.getSessionGeneration()
    )
      throw expiredRequest();

    return response;
  };

  return {
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
}

export type Api = ReturnType<typeof createApi>;
