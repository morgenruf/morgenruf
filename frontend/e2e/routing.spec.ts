import { expect, test } from '@playwright/test';

import { backend } from './environment';

test.beforeEach(async ({ request }) => {
  expect((await request.post(`${backend}/__test__/reset`)).ok()).toBeTruthy();
});

test('intent preloading and page hooks share one fresh session and member request', async ({
  page,
  context,
}) => {
  await context.request.post(`${backend}/__test__/session?role=admin`);

  const reads: string[] = [];

  page.on('request', (request) => {
    if (request.method() === 'GET') reads.push(new URL(request.url()).pathname);
  });
  await page.goto('/dashboard/automation');

  await expect(
    page.getByRole('heading', { name: 'Automation', exact: true }),
  ).toBeVisible();

  const members = page.getByRole('link', { name: 'Members', exact: true });

  await members.hover();
  await expect
    .poll(
      () => reads.filter((path) => path === '/dashboard/api/members').length,
    )
    .toBe(1);
  await members.click();

  await expect(
    page.getByRole('heading', { name: 'Members', exact: true }),
  ).toBeVisible();
  await expect(page.locator('[data-loading-skeleton]')).toHaveCount(0);
  expect(
    reads.filter((path) => path === '/dashboard/api/members'),
  ).toHaveLength(1);
  expect(reads.filter((path) => path === '/dashboard/api/me')).toHaveLength(1);
});

test('malformed bookmarks recover and literal text filters survive refresh', async ({
  page,
  context,
}) => {
  await context.request.post(`${backend}/__test__/session?role=admin`);
  await page.goto(
    '/dashboard/standups?q=123&status=invalid&edit=invalid&new=false',
  );

  const input = page.getByRole('textbox', { name: 'Search standups' });

  await expect(input).toHaveValue('123');
  await expect(page.getByRole('dialog')).toHaveCount(0);

  await input.fill('true');

  await expect(input).toBeFocused();

  await page.reload();

  await expect(input).toHaveValue('true');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

for (const { path, label, endpoint, age } of [
  {
    path: '/dashboard/standups?status=active',
    label: 'Search standups',
    endpoint: 'me',
    age: 61_000,
  },
  {
    path: '/dashboard/members?role=admin',
    label: 'Search members',
    endpoint: 'me',
    age: 61_000,
  },
  {
    path: '/dashboard/standups?status=active',
    label: 'Search standups',
    endpoint: 'modules',
    age: 31_000,
  },
]) {
  test(`${label} preserves typing while stale ${endpoint} refreshes`, async ({
    page,
    context,
  }) => {
    await context.request.post(`${backend}/__test__/session?role=admin`);
    await page.goto(path);

    const input = page.getByRole('textbox', { name: label });

    await expect(input).toBeVisible();
    await expect(page.locator('[data-loading-skeleton]')).toHaveCount(0);

    let release!: () => void;
    const ready = new Promise<void>((resolve) => {
      release = resolve;
    });
    const pattern = `**/dashboard/api/${endpoint}`;

    await page.route(pattern, async (route) => {
      await ready;
      await route.continue();
    });
    await page.clock.setFixedTime(Date.now() + age);

    const refreshing = page.waitForRequest(pattern);
    const refreshed = page.waitForResponse(pattern);

    try {
      await input.pressSequentially('D');
      await refreshing;
      await input.pressSequentially('aily', { delay: 50 });

      await expect(input).toHaveValue('Daily');
      await expect(input).toBeFocused();
      await expect(page).toHaveURL(
        (url) => url.searchParams.get('q') === 'Daily',
      );

      await input.press('Backspace');

      await expect(input).toHaveValue('Dail');

      await input.fill('');
      await input.pressSequentially('true', { delay: 50 });

      await expect(input).toHaveValue('true');
    } finally {
      release();
      await refreshed;
    }

    await expect(input).toHaveValue('true');
    await expect(input).toBeFocused();
    await expect(page).toHaveURL((url) => url.searchParams.get('q') === 'true');

    for (const [key, value] of new URL(path, backend).searchParams)
      await expect(page).toHaveURL(
        (url) => url.searchParams.get(key) === value,
      );

    await page.reload();

    await expect(input).toHaveValue('true');
  });
}

test('unknown dashboard paths and result routes never bootstrap a private session', async ({
  page,
}) => {
  const privateReads: string[] = [];

  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/dashboard/api/'))
      privateReads.push(request.url());
  });
  await page.goto('/dashboard/unknown-screen');

  await expect(
    page.getByRole('heading', { name: 'Page not found' }),
  ).toBeVisible();

  await page.goto('/auth/result?status=&result=success');

  await expect(
    page.getByRole('heading', { name: 'Something went wrong' }),
  ).toBeVisible();

  await page.goto('/dashboard/login?error=invalid-link');

  await expect(page.getByRole('alert')).toContainText('invalid or has expired');
  expect(privateReads).toEqual([]);
});
