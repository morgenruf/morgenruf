import { expect, test, type Page, type Route } from '@playwright/test';

import { productionBackend as backend } from '../environment';

test.beforeEach(async ({ request }) => {
  expect((await request.post(`${backend}/__test__/reset`)).ok()).toBeTruthy();
});

async function holdApplicationScripts(page: Page) {
  let release!: () => void;
  const scriptsReady = new Promise<void>((resolve) => {
    release = resolve;
  });

  const handler = async (route: Route) => {
    if (route.request().resourceType() === 'script') await scriptsReady;

    await route.continue();
  };

  await page.route('**/*', handler);

  // Let pending handlers finish; removing the route can continue them twice.
  return release;
}

for (const [device, viewport] of [
  ['desktop', { width: 1280, height: 900 }],
  ['mobile', { width: 390, height: 844 }],
] as const) {
  test(`dashboard visits and refreshes show the workspace before application scripts load on ${device}`, async ({
    page,
    context,
  }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.emulateMedia({
      colorScheme: device === 'desktop' ? 'dark' : 'light',
      reducedMotion: 'reduce',
    });

    expect(
      (
        await context.request.post(`${backend}/__test__/session?role=admin`)
      ).ok(),
    ).toBeTruthy();

    const errors: string[] = [];
    const privateRequests: string[] = [];

    page.on('pageerror', (error) => errors.push(error.message));
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text());
    });
    page.on('request', (request) => {
      if (request.url().includes('/dashboard/api/'))
        privateRequests.push(request.url());
    });

    for (const navigation of ['visit', 'refresh'] as const) {
      const release = await holdApplicationScripts(page);

      privateRequests.length = 0;

      try {
        const response =
          navigation === 'visit'
            ? await page.goto('/dashboard/analytics', { waitUntil: 'commit' })
            : await page.reload({ waitUntil: 'commit' });

        expect(response?.status()).toBe(200);

        const dashboard = page.locator('[data-startup-dashboard]');

        await expect(dashboard).toBeVisible();
        await expect(
          page.getByRole('status', { name: 'Opening your workspace…' }),
        ).toBeVisible();
        await expect(page.locator('[data-startup-public]')).toBeHidden();
        await expect(
          dashboard.locator('main [data-slot="skeleton"]').first(),
        ).toBeVisible();

        if (device === 'desktop') {
          await expect(page.locator('html')).toHaveClass(/\bdark\b/);
          await expect(dashboard.locator('aside')).toBeVisible();
          await expect(
            dashboard.locator('aside [data-slot="skeleton"]').first(),
          ).toBeVisible();
        } else {
          await expect(dashboard.locator('aside')).toBeHidden();
          expect(
            await page
              .locator('html')
              .evaluate((element) => element.scrollWidth),
          ).toBeLessThanOrEqual(viewport.width);
        }

        expect(privateRequests).toEqual([]);

        if (navigation === 'visit')
          await page.screenshot({
            path: testInfo.outputPath('dashboard-initial-shell.png'),
          });
      } finally {
        release();
      }

      await expect(page.getByRole('heading', { level: 1 })).toContainText(
        'Analytics',
      );
      await expect(page.locator('[data-loading-skeleton]')).toHaveCount(0);
    }

    expect(errors).toEqual([]);
  });
}

test('the login document keeps the public fallback before application scripts load', async ({
  page,
}) => {
  const errors: string[] = [];
  const privateRequests: string[] = [];

  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('request', (request) => {
    if (request.url().includes('/dashboard/api/'))
      privateRequests.push(request.url());
  });

  const release = await holdApplicationScripts(page);

  try {
    expect(
      (await page.goto('/dashboard/login', { waitUntil: 'commit' }))?.status(),
    ).toBe(200);

    await expect(page.locator('[data-startup-public]')).toBeVisible();
    await expect(page.locator('[data-startup-dashboard]')).toBeHidden();
    expect(privateRequests).toEqual([]);
  } finally {
    release();
  }

  await expect(page.getByRole('heading', { level: 1 })).toContainText(
    "Your team's morning call",
  );
  expect(privateRequests).toEqual([]);
  expect(errors).toEqual([]);
});

test('the static shell contains no private data and preserves asset caching', async ({
  request,
}) => {
  const response = await request.get('/_shell.html');

  expect(response.status()).toBe(200);
  expect(response.headers()['cache-control']).toBe('no-cache');

  const shell = await response.text();

  expect(shell).toContain('<html');

  expect(
    (await request.post(`${backend}/__test__/session?role=admin`)).ok(),
  ).toBeTruthy();

  const authenticatedShell = await request.get('/dashboard/reports');

  expect(await authenticatedShell.text()).toBe(shell);

  for (const privateValue of [
    'csrf_token',
    'U_ADMIN',
    'Alex Morgan',
    'Northstar Studio',
    'manager@example.test',
    'must-never-be-public',
    'browser-tests-only-not-a-production-secret',
  ]) {
    expect(shell).not.toContain(privateValue);
  }

  const assetPaths = [
    ...new Set(
      [...shell.matchAll(/(?:src|href)="(\/assets\/[^"?#]+)[^"]*"/g)].map(
        (match) => match[1],
      ),
    ),
  ];

  expect(assetPaths.some((asset) => asset.endsWith('.js'))).toBeTruthy();
  expect(assetPaths.some((asset) => asset.endsWith('.css'))).toBeTruthy();

  for (const asset of assetPaths) {
    const result = await request.get(asset);

    expect(result.status(), asset).toBe(200);
    expect(result.headers()['cache-control']).toContain('immutable');
    expect(result.headers()['content-type']).not.toContain('text/html');
  }

  expect((await request.get('/static/icon-192.png')).status()).toBe(200);

  for (const missing of ['/assets/missing.js', '/static/missing.png']) {
    const result = await request.get(missing);

    expect(result.status()).toBe(404);
    expect(await result.text()).not.toBe(shell);
  }
});

test('deep links and refreshes hydrate from the production shell', async ({
  page,
  context,
}) => {
  expect(
    (await context.request.post(`${backend}/__test__/session?role=admin`)).ok(),
  ).toBeTruthy();

  const errors: string[] = [];

  page.on('pageerror', (error) =>
    errors.push(`${page.url()}: ${error.message}`),
  );
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });

  for (const [url, title] of [
    ['/dashboard/', 'Standups'],
    ['/dashboard/standups', 'Standups'],
    ['/dashboard/connect/1', 'Friday coffee'],
    ['/dashboard/analytics?schedule=1', 'Analytics'],
  ]) {
    expect((await page.goto(url))?.status()).toBe(200);
    await expect(page.getByRole('heading', { level: 1 })).toContainText(title);

    await page.reload();

    await expect(page.getByRole('heading', { level: 1 })).toContainText(title);
  }

  expect(errors).toEqual([]);
});

test('backend routes stay proxied and login tokens never enter the shell', async ({
  page,
  request,
}) => {
  const session = await request.get('/dashboard/api/me');

  expect(session.status()).toBe(401);
  expect(session.headers()['content-type']).toContain('application/json');

  for (const url of [
    '/api/unknown',
    '/dashboard/api/unknown',
    '/mcp/unknown',
  ]) {
    const response = await request.get(url);

    expect(response.status()).toBe(404);
    expect(await response.text()).not.toContain('/assets/');
  }

  const invalid = await request.get('/dashboard?t=invalid', {
    maxRedirects: 0,
  });

  expect(invalid.status()).toBe(303);
  expect(invalid.headers().location).toBe(
    '/dashboard/login?error=invalid-link',
  );

  const link = await (
    await request.get(`${backend}/__test__/login-link`)
  ).json();
  const tokenResponse = await request.get(link.url, { maxRedirects: 0 });

  expect(tokenResponse.status()).toBe(303);
  expect(tokenResponse.headers().location).toBe('/dashboard/');
  expect(tokenResponse.headers()['cache-control']).toBe('no-store');

  await page.goto(`${link.url}#reports`);

  await expect(page).toHaveURL(/\/dashboard\/reports$/);
  await expect(
    page.getByRole('heading', { name: 'Reports', exact: true }),
  ).toBeVisible();

  await page.goto('/dashboard/#schedules');

  await expect(page).toHaveURL(/\/dashboard\/standups$/);
  await expect(
    page.getByRole('heading', { name: 'Standups', exact: true }),
  ).toBeVisible();
});

test('public routes hydrate without starting a private session', async ({
  page,
}) => {
  const privateRequests: string[] = [];
  const errors: string[] = [];

  page.on('request', (request) => {
    if (request.url().includes('/dashboard/api/'))
      privateRequests.push(request.url());
  });
  page.on('pageerror', (error) =>
    errors.push(`${page.url()}: ${error.message}`),
  );
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });

  for (const [url, heading] of [
    ['/dashboard/login', "Your team's morning call"],
    ['/auth/result?status=success', 'You are all set'],
    ['/email/result?status=subscribed', 'Email updates enabled'],
    ['/connect/zoom/result?status=connected', 'Account connected'],
    ['/feed/public-browser-feed', 'Northstar daily update'],
    ['/not-a-real-page', 'Page not found'],
  ]) {
    expect((await page.goto(url))?.status()).toBe(200);
    await expect(page.getByRole('heading', { level: 1 })).toContainText(
      heading,
    );
  }

  expect(privateRequests).toEqual([]);
  expect(errors).toEqual([]);
});
