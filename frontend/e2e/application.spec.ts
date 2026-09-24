import { expect, test, type BrowserContext, type Page } from '@playwright/test';

import { backend } from './environment';

async function signIn(context: BrowserContext, role = 'admin') {
  const response = await context.request.post(
    `${backend}/__test__/session?role=${role}`,
  );

  expect(response.ok()).toBe(true);
}

async function chooseOption(page: Page, name: string, option: string) {
  await page.getByRole('combobox', { name, exact: true }).click();
  await page.getByRole('option', { name: option, exact: true }).click();
}

test.beforeEach(async ({ request }) => {
  const response = await request.post(`${backend}/__test__/reset`);

  expect(response.ok()).toBe(true);
});

test('authentication, signed legacy links, hash bookmarks, and logout', async ({
  page,
  context,
  request,
}) => {
  await page.goto('/dashboard/standups');

  await expect(page).toHaveURL(/\/dashboard\/login/);
  await expect(page.getByRole('link', { name: /slack/i })).toBeVisible();

  const link = await (
    await request.get(`${backend}/__test__/login-link`)
  ).json();

  await page.goto(`${link.url}#reports`);

  await expect(page).toHaveURL(/\/dashboard\/reports$/);
  await expect(
    page.getByRole('heading', { name: 'Reports', exact: true }),
  ).toBeVisible();
  await expect(page).not.toHaveURL(/[?&]t=/);

  await page.reload();

  await expect(
    page.getByRole('heading', { name: 'Reports', exact: true }),
  ).toBeVisible();

  await page.goto('/dashboard/#schedules');

  await expect(page).toHaveURL(/\/dashboard\/standups$/);
  await expect(
    page.getByRole('heading', { name: 'Standups', exact: true }),
  ).toBeVisible();

  await page.getByRole('button', { name: 'Sign out', exact: true }).click();

  await expect(page).toHaveURL(/\/dashboard\/login/);
  expect(
    (await context.request.get(`${backend}/dashboard/api/me`)).status(),
  ).toBe(401);
});

test('every migrated feature renders against the Flask contract', async ({
  page,
  context,
}) => {
  await signIn(context);

  const errors: string[] = [];

  page.on('pageerror', (error) => errors.push(error.message));

  for (const [route, title] of [
    ['standups', 'Standups'],
    ['today', 'Good morning|Good afternoon|Good evening'],
    ['connect', 'Coffee chats'],
    ['kudos', 'Kudos'],
    ['members', 'Members'],
    ['insights', 'Insights'],
    ['reports', 'Reports'],
    ['analytics', 'Analytics'],
    ['settings', 'Settings'],
    ['automation', 'Automation'],
    ['webhooks', 'Webhooks'],
    ['mcp', 'MCP'],
  ]) {
    await test.step(title, async () => {
      await page.goto(`/dashboard/${route}`);

      await expect(page.getByRole('heading', { level: 1 })).toContainText(
        new RegExp(title, 'i'),
      );

      await page.waitForLoadState('networkidle');

      await expect(page.getByText('Could not load this view')).toHaveCount(0);
      await expect(
        page.getByText('Something went wrong', { exact: true }),
      ).toHaveCount(0);
    });
  }

  expect(errors).toEqual([]);
});

test('standup creation uses CSRF and survives refresh', async ({
  page,
  context,
}) => {
  await signIn(context);

  expect(
    (
      await context.request.post(`${backend}/dashboard/api/standups`, {
        data: { name: 'Rejected without CSRF' },
      })
    ).status(),
  ).toBe(403);

  await page.goto('/dashboard/standups');
  await page
    .getByRole('button', { name: /New standup/i })
    .first()
    .click();

  const dialog = page.getByRole('dialog');

  await dialog
    .getByLabel('Standup name', { exact: true })
    .fill('Frontend migration check');

  const channel = dialog.getByRole('combobox', {
    name: 'Channel',
    exact: true,
  });

  await dialog
    .getByRole('button', { name: 'Save standup', exact: true })
    .click();

  await expect(
    dialog.getByText('Choose a channel.', { exact: true }),
  ).toBeVisible();
  await expect(channel).toHaveAttribute('aria-invalid', 'true');
  await expect(channel).toBeFocused();

  await channel.click();
  await page.getByRole('option', { name: '#engineering', exact: true }).click();

  await dialog
    .getByRole('button', { name: 'Save standup', exact: true })
    .click();

  await expect(dialog).toBeHidden();
  await expect(
    page.getByText('Frontend migration check', { exact: true }),
  ).toBeVisible();

  await page.reload();

  await expect(
    page.getByText('Frontend migration check', { exact: true }),
  ).toBeVisible();
});

test('coffee chat creation, details, and attendance have refreshable routes', async ({
  page,
  context,
}) => {
  await signIn(context);
  await page.goto('/dashboard/connect/new');

  await page.getByLabel('Name', { exact: true }).fill('Browser coffee check');

  const channel = page.getByRole('combobox', {
    name: 'Draw people from',
    exact: true,
  });

  await page
    .getByRole('button', { name: 'Create coffee chat', exact: true })
    .click();

  await expect(
    page.getByText('Choose a channel.', { exact: true }),
  ).toBeVisible();
  await expect(channel).toHaveAttribute('aria-invalid', 'true');
  await expect(channel).toBeFocused();
  await expect(page).toHaveURL(/\/dashboard\/connect\/new$/);

  await channel.click();
  await page.getByRole('option', { name: '#engineering', exact: true }).click();

  await page
    .getByRole('button', { name: 'Create coffee chat', exact: true })
    .click();

  await expect(page).toHaveURL(/\/dashboard\/connect\/\d+$/);
  await expect(
    page.getByRole('heading', { name: 'Browser coffee check', exact: true }),
  ).toBeVisible();

  await page.reload();

  await expect(page.getByLabel('Name', { exact: true })).toHaveValue(
    'Browser coffee check',
  );

  await page.getByRole('link', { name: 'View attendance →' }).click();

  await expect(page).toHaveURL(
    /\/dashboard\/connect\/attendance\?program=\d+$/,
  );

  await page.reload();

  await expect(
    page.getByRole('heading', { name: 'Coffee chat attendance', exact: true }),
  ).toBeVisible();
});

test('member permissions hide privileged actions and API rejects writes', async ({
  page,
  context,
}) => {
  await signIn(context, 'member');
  await page.goto('/dashboard/standups');

  await expect(
    page.getByRole('heading', { name: 'Standups', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: /New standup/i })).toHaveCount(
    0,
  );

  await page.goto('/dashboard/members');

  await expect(
    page.getByRole('button', { name: /Invite admin|Make admin|Make member/i }),
  ).toHaveCount(0);

  const session = await (
    await context.request.get(`${backend}/dashboard/api/me`)
  ).json();
  const denied = await context.request.post(
    `${backend}/dashboard/api/mcp/keys`,
    {
      headers: { 'X-CSRF-Token': session.csrf_token },
      data: { name: 'Not allowed' },
    },
  );

  expect(denied.status()).toBe(403);
});

test('webhook and MCP secrets disappear after dismissal', async ({
  page,
  context,
}) => {
  await signIn(context);
  await page.goto('/dashboard/webhooks');

  await page.getByRole('button', { name: 'Add webhook', exact: true }).click();
  await page
    .getByLabel('Destination URL')
    .fill('https://hooks.example.test/morgenruf-events');
  await page.getByRole('button', { name: 'Save webhook', exact: true }).click();

  const webhookSecret = page.getByTestId('one-time-secret');

  await expect(webhookSecret).toBeVisible();

  const secret = await webhookSecret.textContent();

  expect(secret?.length).toBeGreaterThan(20);

  await page.getByRole('button', { name: 'Done', exact: true }).click();

  await expect(webhookSecret).toHaveCount(0);

  await page.reload();

  if (secret)
    await expect(page.getByText(secret, { exact: true })).toHaveCount(0);

  await page.goto('/dashboard/mcp');

  await page.getByRole('button', { name: 'Generate key', exact: true }).click();
  await page.getByLabel('Key name').fill('Browser test assistant');
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Generate key', exact: true })
    .click();

  await expect(page.getByTestId('one-time-secret')).toBeVisible();

  const apiKey = await page.getByTestId('one-time-secret').textContent();

  await page.getByRole('button', { name: 'Done', exact: true }).click();
  await page.reload();

  await expect(
    page.getByText('Browser test assistant', { exact: true }),
  ).toBeVisible();

  if (apiKey)
    await expect(page.getByText(apiKey, { exact: true })).toHaveCount(0);
});

test('report filters persist in URLs and CSV downloads use the backend', async ({
  page,
  context,
}) => {
  await signIn(context);
  await page.goto('/dashboard/reports');

  await page.getByLabel('From', { exact: true }).fill('2026-09-01');
  await page.getByLabel('To', { exact: true }).fill('2026-09-19');

  await expect(page).toHaveURL(/date_from=2026-09-01/);

  await page.reload();

  await expect(page.getByLabel('From', { exact: true })).toHaveValue(
    '2026-09-01',
  );

  const download = page.waitForEvent('download');

  await page.getByRole('button', { name: 'Export CSV', exact: true }).click();

  expect((await download).suggestedFilename()).toMatch(/\.csv$/);
});

test('public feed and integration result pages need no session', async ({
  page,
}) => {
  await page.goto('/feed/public-browser-feed');

  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByText('Could not load this view')).toHaveCount(0);

  await page.goto('/feed/invalid-token');

  await expect(
    page.getByText(/not found|not available|not public/i).first(),
  ).toBeVisible();

  await page.goto('/connect/zoom/callback?error=access_denied');

  await expect(page).toHaveURL(/\/connect\/zoom\/result\?status=/);
  await expect(
    page.getByRole('heading', { name: /cancelled|not connected|not valid/i }),
  ).toBeVisible();

  await page.goto('/oauth/callback?state=invalid');

  await expect(page).toHaveURL(/\/auth\/result\?status=invalid/);

  await page.goto('/email/unsubscribe?t=invalid');

  await expect(page).toHaveURL(/\/email\/result\?status=invalid/);
});

test('shadcn sidebar sizing, tooltips, keyboard controls, and collapsed sign-out', async ({
  page,
  context,
}, testInfo) => {
  await signIn(context);
  await page.goto('/dashboard/members');

  const sidebar = page.locator('[data-slot="sidebar-container"]');
  const members = page
    .getByRole('navigation', { name: 'Main navigation' })
    .getByRole('link', { name: 'Members', exact: true });

  for (const theme of ['light', 'dark']) {
    await page.evaluate(
      (value) => localStorage.setItem('morgenruf-theme', value),
      theme,
    );
    await page.reload();

    await expect(
      page.getByRole('button', { name: 'Collapse sidebar' }),
    ).toBeVisible();
    await expect(sidebar).toHaveCSS('width', '256px');
    await expect(members).toHaveAttribute('aria-current', 'page');
    await expect(page.getByRole('main')).toHaveCount(1);
    await expect(page.locator('[data-loading-skeleton]')).toHaveCount(0);

    await page.screenshot({
      animations: 'disabled',
      path: testInfo.outputPath(`sidebar-expanded-${theme}.png`),
    });
    await page.getByRole('button', { name: 'Collapse sidebar' }).click();

    await expect(sidebar).toHaveCSS('width', '48px');
    await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();

    await members.hover();

    const tooltip = page.locator('[data-slot="tooltip-content"]');

    await expect(tooltip).toBeVisible();
    await expect(tooltip).toHaveText('Members');

    await page.screenshot({
      animations: 'disabled',
      path: testInfo.outputPath(`sidebar-collapsed-${theme}.png`),
    });

    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);

    await members.focus();
    await page.keyboard.press('Control+b');

    await expect(
      page.getByRole('button', { name: 'Collapse sidebar' }),
    ).toBeVisible();
    await expect(members).toBeFocused();

    await page.keyboard.press('Meta+b');

    await expect(
      page.getByRole('button', { name: 'Expand sidebar' }),
    ).toBeVisible();
  }

  await page.getByRole('button', { name: 'Sign out', exact: true }).click();

  await expect(page).toHaveURL(/\/dashboard\/login/);
});

test('mobile navigation and stored dark appearance work without overflow', async ({
  page,
  context,
}, testInfo) => {
  await signIn(context);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() =>
    localStorage.setItem('morgenruf-theme', 'dark'),
  );

  await page.goto('/dashboard/standups');

  await expect(page.locator('html')).toHaveClass(/dark/);
  await expect(
    page.getByRole('button', { name: 'New standup', exact: true }),
  ).toBeVisible();

  const trigger = page.getByRole('button', {
    name: 'Open navigation',
    exact: true,
  });

  await trigger.click();

  const dialog = page.getByRole('dialog');

  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveCSS('width', '288px');
  await expect(dialog.getByRole('button', { name: 'Sign out' })).toBeVisible();
  await expect(dialog).toHaveCSS('opacity', '1');

  await page.screenshot({
    animations: 'disabled',
    path: testInfo.outputPath('mobile-sidebar-dark.png'),
  });
  await dialog.getByRole('button', { name: 'Close navigation' }).click();

  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();

  await trigger.click();
  await page.keyboard.press('Escape');

  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();

  await trigger.click();
  await page
    .getByRole('dialog')
    .getByRole('link', { name: 'Members', exact: true })
    .click();

  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(
    page.getByRole('heading', { name: 'Members', exact: true }),
  ).toBeVisible();

  await expect(trigger).toBeFocused();

  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);

  await page.keyboard.press('Tab');

  expect(await page.evaluate(() => document.activeElement?.tagName)).not.toBe(
    'BODY',
  );

  const roleFilter = page.getByRole('combobox', { name: 'Filter by role' });

  await roleFilter.click();

  const popup = page.getByRole('listbox');

  await expect(popup).toBeVisible();

  const bounds = await popup.boundingBox();

  expect(bounds).not.toBeNull();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  expect(bounds!.y).toBeGreaterThanOrEqual(0);
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(844);

  await page.getByRole('option', { name: 'Admins', exact: true }).click();

  await expect(roleFilter).toContainText('Admins');
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);

  await page.getByRole('button', { name: 'Choose appearance' }).click();
  await page.getByRole('menuitem', { name: 'Light', exact: true }).click();

  await expect(page.locator('html')).not.toHaveClass(/dark/);

  await trigger.click();

  await expect(dialog).toHaveCSS('opacity', '1');

  await page.screenshot({
    animations: 'disabled',
    path: testInfo.outputPath('mobile-sidebar-light.png'),
  });
  await dialog.getByRole('button', { name: 'Sign out', exact: true }).click();

  await expect(page).toHaveURL(/\/dashboard\/login/);
});

for (const filter of [
  {
    route: 'members?q=Alex',
    name: 'Filter by role',
    option: 'Admins',
    key: 'role',
    value: 'admin',
    reset: 'All roles',
    keep: ['q', 'Alex'],
  },
  {
    route: 'reports?date_from=2026-09-01',
    name: 'Member',
    option: 'Alex Morgan',
    key: 'user_id',
    value: 'U_ADMIN',
    reset: 'All members',
    keep: ['date_from', '2026-09-01'],
  },
  {
    route: 'analytics?days=30',
    name: 'Standup',
    option: 'Engineering standup',
    key: 'schedule',
    value: '1',
    reset: 'All standups',
    keep: ['days', '30'],
  },
]) {
  test(`${filter.name} selects, survives refresh, and clears without dropping other filters`, async ({
    page,
    context,
  }) => {
    await signIn(context);
    await page.goto(`/dashboard/${filter.route}`);
    await chooseOption(page, filter.name, filter.option);

    await expect(page).toHaveURL(
      new RegExp(`[?&]${filter.key}=${filter.value}`),
    );

    await page.reload();

    await expect(
      page.getByRole('combobox', { name: filter.name, exact: true }),
    ).toContainText(filter.option);

    await chooseOption(page, filter.name, filter.reset);

    await expect(page).not.toHaveURL(new RegExp(`[?&]${filter.key}=`));
    await expect(page).toHaveURL(
      new RegExp(`[?&]${filter.keep[0]}=${filter.keep[1]}`),
    );
  });
}

test('leaderboard periods and attendance program choices survive refresh', async ({
  page,
  context,
}) => {
  await signIn(context);
  await page.goto('/dashboard/kudos');
  await chooseOption(page, 'Leaderboard period', 'Last 90 days');

  await expect(page).toHaveURL(/days=90/);

  await page.reload();

  await expect(
    page.getByRole('combobox', { name: 'Leaderboard period' }),
  ).toContainText('Last 90 days');

  await page.goto('/dashboard/connect/new');
  await page.getByLabel('Name', { exact: true }).fill('Second coffee');
  await chooseOption(page, 'Draw people from', '#engineering');
  await page
    .getByRole('button', { name: 'Create coffee chat', exact: true })
    .click();

  await expect(page).toHaveURL(/\/dashboard\/connect\/\d+$/);

  await page.goto('/dashboard/connect/attendance?program=1');

  await expect(
    page.getByRole('combobox', { name: 'Coffee chat', exact: true }),
  ).toContainText('Friday coffee');

  await chooseOption(page, 'Coffee chat', 'Second coffee');

  await expect(page).toHaveURL(/program=2/);

  await page.reload();

  await expect(
    page.getByRole('combobox', { name: 'Coffee chat', exact: true }),
  ).toContainText('Second coffee');
});

test('select keyboard navigation and Escape work inside a standup dialog', async ({
  page,
  context,
}) => {
  await signIn(context);
  await page.goto('/dashboard/standups?edit=1');

  const dialog = page.getByRole('dialog');
  const channel = dialog.getByRole('combobox', {
    name: 'Channel',
    exact: true,
  });

  await expect(channel).toContainText('#engineering');

  await channel.focus();
  await page.keyboard.press('Space');

  await expect(page.getByRole('listbox')).toBeVisible();

  await page.keyboard.press('Escape');

  await expect(page.getByRole('listbox')).toBeHidden();
  await expect(dialog).toBeVisible();
  await expect(channel).toBeFocused();

  await page.keyboard.press('Space');

  await expect(page.getByRole('listbox')).toBeVisible();
  await expect(
    page.getByRole('option', { name: '#engineering', exact: true }),
  ).toBeFocused();

  await page.keyboard.press('End');

  await expect(
    page.getByRole('option', { name: '#general', exact: true }),
  ).toBeFocused();

  await page.keyboard.press('Enter');

  await expect(channel).toContainText('#general');
  await expect(dialog).toBeVisible();
  await expect(channel).toBeFocused();

  await dialog
    .getByRole('button', { name: 'Save standup', exact: true })
    .click();

  await expect(dialog).toBeHidden();

  await page.goto('/dashboard/standups?edit=1');

  await expect(
    page.getByRole('combobox', { name: 'Channel', exact: true }),
  ).toContainText('#general');
});
