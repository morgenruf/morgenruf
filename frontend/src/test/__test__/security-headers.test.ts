// @vitest-environment node
import { readFileSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), 'utf8');

const include = 'include /etc/nginx/snippets/security-headers.conf;';

describe('Nginx security headers', () => {
  it('refuses framing and sniffing', () => {
    const snippet = read('../../../nginx-security-headers.conf');

    expect(snippet).toContain('add_header X-Frame-Options "DENY" always;');
    expect(snippet).toContain(
      `add_header Content-Security-Policy "frame-ancestors 'none'" always;`,
    );
    expect(snippet).toContain(
      'add_header X-Content-Type-Options "nosniff" always;',
    );
  });

  it('repeats the include wherever a location sets its own headers', () => {
    const nginx = read('../../../nginx.conf.template');
    const server = nginx.slice(0, nginx.indexOf('location'));
    const locations = [
      ...nginx.matchAll(/location\s+[^{]*\{([^}]*)\}/g),
    ].filter((match) => match[1].includes('add_header'));

    expect(server).toContain(include);
    expect(locations.length).toBeGreaterThan(0);
    for (const match of locations) expect(match[1]).toContain(include);
  });

  it('ships the snippet in the image', () => {
    expect(read('../../../Dockerfile')).toContain(
      'COPY frontend/nginx-security-headers.conf /etc/nginx/snippets/security-headers.conf',
    );
  });
});
