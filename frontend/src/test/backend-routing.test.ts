// @vitest-environment node
import { readFileSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import {
  backendExactPaths,
  backendNamespacePrefixes,
  backendProxyPatterns,
} from '../../config/backend-routes';

const matchesBackend = (url: string) =>
  backendProxyPatterns.some((pattern) =>
    pattern.startsWith('^')
      ? new RegExp(pattern).test(url)
      : url.startsWith(pattern),
  );

describe('development and production routing parity', () => {
  it('uses the same backend exact routes and namespaces as Nginx', () => {
    const nginx = readFileSync(
      new URL('../../nginx.conf.template', import.meta.url),
      'utf8',
    );
    const locations = [
      ...nginx.matchAll(/location\s+(=)?\s*(\/[^\s{]*)\s*\{([^}]*)\}/g),
    ].filter((match) => match[3].includes('proxy_pass'));

    expect(backendExactPaths.toSorted()).toEqual(
      locations
        .filter((match) => match[1])
        .map((match) => match[2])
        .toSorted(),
    );
    expect(backendNamespacePrefixes.toSorted()).toEqual(
      locations
        .filter((match) => !match[1])
        .map((match) => match[2])
        .toSorted(),
    );
  });

  it.each([
    '/dashboard/api',
    '/api',
    '/slack',
    '/google',
    '/webhooks',
    '/mcp',
    '/api/unknown',
    '/dashboard/api/unknown',
    '/mcp/unknown',
    '/dashboard?t=login-token',
    '/oauth/callback?state=signed',
  ])('reserves %s for the backend', (url) => {
    expect(matchesBackend(url)).toBe(true);
  });

  it.each([
    '/dashboard/',
    '/dashboard/login',
    '/dashboard/standups',
    '/dashboard/connect/12',
    '/feed/opaque-token',
    '/auth/result',
    '/email/result',
    '/connect/zoom/result',
    '/mcp-guide',
    '/openapi.json-preview',
    '/healthz-status',
    '/oauth/callback/extra',
  ])('leaves %s to the frontend', (url) => {
    expect(matchesBackend(url)).toBe(false);
  });
});
