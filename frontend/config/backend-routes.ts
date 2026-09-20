/** Match production's reserved backend routes, including bare API namespaces. */
export const backendExactPaths = [
  '/dashboard',
  '/dashboard/logout',
  '/install',
  '/oauth/callback',
  '/email/subscribe',
  '/email/unsubscribe',
  '/connect/zoom/start',
  '/connect/zoom/callback',
  '/healthz',
  '/openapi.json',
  '/dashboard/api',
  '/api',
  '/slack',
  '/google',
  '/webhooks',
  '/mcp',
];

export const backendNamespacePrefixes = [
  '/dashboard/api/',
  '/api/',
  '/slack/',
  '/google/',
  '/webhooks/',
  '/mcp/',
];

const escapeRegex = (path: string) =>
  path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export const backendProxyPatterns = [
  ...backendExactPaths.map((path) => `^${escapeRegex(path)}(?:\\?.*)?$`),
  ...backendNamespacePrefixes,
];
