import { expect, test, type Page, type Route } from '@playwright/test';

import { backend } from './environment';

async function hold(page: Page, pattern: string | RegExp) {
  let release!: () => void;
  const ready = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(pattern, async (route: Route) => {
    await ready;
    await route.continue();
  });
  return release;
}

test.beforeEach(async ({ request, context }) => {
  expect((await request.post(`${backend}/__test__/reset`)).ok()).toBeTruthy();
  expect(
    (await context.request.post(`${backend}/__test__/session?role=admin`)).ok(),
  ).toBeTruthy();
});

for (const [path, endpoint, label] of [
  ['today', 'today', 'Loading today…'],
  ['standups', 'standups', 'Loading standups…'],
  ['connect', 'connect/programs', 'Loading coffee chats…'],
  ['connect/new', 'modules', 'Loading coffee chat form…'],
  ['connect/1', 'connect/programs', 'Loading coffee chat…'],
  ['connect/attendance', 'connect/programs', 'Loading attendance…'],
  ['insights', 'insights', 'Loading insights…'],
  ['reports', 'reports', 'Loading reports…'],
  ['analytics', 'analytics', 'Loading analytics…'],
  ['members', 'members', 'Loading members…'],
  ['kudos', 'kudos/leaderboard', 'Loading leaderboard…'],
  ['settings', 'standups', 'Loading standup settings…'],
  ['automation', 'rules', 'Loading automation…'],
  ['webhooks', 'webhooks', 'Loading webhooks…'],
  ['mcp', 'mcp/keys', 'Loading API keys…'],
]) {
  test(`delayed ${path} content has a responsive skeleton`, async ({
    page,
  }, testInfo) => {
    const release = await hold(
      page,
      new RegExp(`/dashboard/api/${endpoint}(\\?.*)?$`),
    );
    await page.goto(`/dashboard/${path}`);
    await expect(
      page.getByRole('status', { name: label, exact: true }),
    ).toBeVisible();
    await expect(
      page.locator('main [data-slot="skeleton"]').first(),
    ).toBeVisible();
    await expect(
      page.getByRole('navigation', { name: 'Main navigation' }),
    ).toBeVisible();
    await expect(
      page.locator(
        '[data-loading-skeleton] button, [data-loading-skeleton] input, [data-loading-skeleton] a',
      ),
    ).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath('desktop-loading.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(
      page.getByRole('status', { name: label, exact: true }),
    ).toBeVisible();
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      )
      .toBe(true);
    await page.screenshot({ path: testInfo.outputPath('mobile-loading.png') });
    release();
    await expect(page.locator('[data-loading-skeleton]')).toHaveCount(0);
    await expect(page.getByText('Could not load this view')).toHaveCount(0);
  });
}

for (const [path, module, label] of [
  ['/dashboard/login', 'auth/pages/login-page', 'Loading sign in…'],
  [
    '/auth/result?status=success',
    'public/pages/result-page',
    'Loading result…',
  ],
  [
    '/email/result?status=subscribed',
    'public/pages/result-page',
    'Loading result…',
  ],
  [
    '/connect/zoom/result?status=connected',
    'public/pages/result-page',
    'Loading result…',
  ],
  [
    '/feed/public-browser-feed',
    'public/pages/feed-page',
    'Loading standup report…',
  ],
]) {
  test(`cold public route ${path} has a matching fallback`, async ({
    page,
  }) => {
    const release = await hold(page, `**/src/modules/${module}.tsx*`);
    await page.goto(path, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-slot="skeleton"]').first()).toBeVisible();
    if (!path.startsWith('/feed/'))
      await expect(page.getByRole('status', { name: label })).toBeVisible();
    release();
    await expect(page.locator('[data-loading-skeleton]')).toHaveCount(0);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  });
}

test('workspace bootstrap uses the requested skeleton and respects dark mode and reduced motion', async ({
  page,
}, testInfo) => {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  const release = await hold(page, '**/dashboard/api/me');
  await page.goto('/dashboard/analytics');
  await expect(
    page.getByRole('status', { name: 'Opening your workspace…' }),
  ).toBeVisible();
  await expect(page.locator('html')).toHaveClass(/dark/);
  await expect(page.locator('[data-slot="skeleton"]').first()).toHaveCSS(
    'animation-name',
    'none',
  );
  await page.screenshot({
    path: testInfo.outputPath('dark-workspace-loading.png'),
  });
  release();
  await expect(page.locator('[data-loading-skeleton]')).toHaveCount(0);
});

test('navigation shows its destination while keeping the collapsed sidebar', async ({
  page,
}) => {
  await page.goto('/dashboard/standups');
  await expect(page.locator('[data-loading-skeleton]')).toHaveCount(0);
  await page.getByRole('button', { name: 'Collapse sidebar' }).click();
  const release = await hold(
    page,
    '**/src/modules/members/pages/members-page.tsx*',
  );
  await page.getByRole('link', { name: 'Members', exact: true }).click();
  await expect(
    page.getByRole('status', { name: 'Loading members…' }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Expand sidebar' }),
  ).toBeVisible();
  release();
  await expect(page).toHaveURL(/\/dashboard\/members$/);
  await expect(page.locator('[data-loading-skeleton]')).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Expand sidebar' }),
  ).toBeVisible();
  const refresh = await hold(page, /\/dashboard\/api\/members(\?.*)?$/);
  const cardText = await page
    .locator('main [data-slot="card"]')
    .first()
    .innerText();
  await page.getByRole('button', { name: /Refresh/ }).click();
  await expect(page.locator('main [data-slot="card"]').first()).toHaveText(
    cardText,
    { useInnerText: true },
  );
  await expect(page.locator('[data-loading-skeleton]')).toHaveCount(0);
  refresh();
});

test('nested participant, pairing, delivery, and invitation loads retain their surrounding UI', async ({
  page,
}) => {
  const participants = await hold(page, /\/dashboard\/api\/members(\?.*)?$/);
  await page.goto('/dashboard/standups');
  await page.getByRole('button', { name: 'New standup', exact: true }).click();
  await page.getByRole('tab', { name: 'Basics', exact: true }).click();
  await expect(
    page.getByRole('status', { name: 'Loading participants…' }),
  ).toBeVisible();
  await expect(
    page.getByRole('textbox', { name: 'Standup name', exact: true }),
  ).toBeVisible();
  participants();
  await expect(
    page.getByRole('status', { name: 'Loading participants…' }),
  ).toHaveCount(0);
  await page.unroute(/\/dashboard\/api\/members(\?.*)?$/);

  const pairings = await hold(
    page,
    '**/dashboard/api/connect/rounds/*/matches',
  );
  await page.goto('/dashboard/connect/attendance');
  await expect(page.locator('[data-loading-skeleton]')).toHaveCount(0);
  await page.getByRole('button', { name: /pairings/ }).click();
  await expect(
    page.getByRole('status', { name: 'Loading pairings…' }),
  ).toBeVisible();
  await expect(page.getByText('By person', { exact: true })).toBeVisible();
  pairings();
  await expect(
    page.getByRole('status', { name: 'Loading pairings…' }),
  ).toHaveCount(0);

  const deliveries = await hold(
    page,
    '**/dashboard/api/webhooks/*/deliveries*',
  );
  await page.goto('/dashboard/webhooks');
  await page
    .getByRole('button', { name: 'Deliveries', exact: true })
    .first()
    .click();
  await expect(
    page.getByRole('status', { name: 'Loading recent deliveries…' }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Hide deliveries' }),
  ).toBeVisible();
  deliveries();
  await expect(
    page.getByRole('status', { name: 'Loading recent deliveries…' }),
  ).toHaveCount(0);

  const invitations = await hold(page, /\/dashboard\/api\/members$/);
  await page.goto('/dashboard/members?channel=C_ENGINEERING');
  await page.getByRole('button', { name: 'Invite admin', exact: true }).click();
  await expect(
    page.getByRole('status', { name: 'Loading members to invite…' }),
  ).toBeVisible();
  await expect(
    page.getByRole('textbox', { name: 'Find a member to invite' }),
  ).toBeVisible();
  invitations();
  await expect(
    page.getByRole('status', { name: 'Loading members to invite…' }),
  ).toHaveCount(0);
});
