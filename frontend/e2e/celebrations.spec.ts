import { expect, test, type BrowserContext, type Page } from '@playwright/test';

import { backend } from './environment';

async function signIn(context: BrowserContext, role: string) {
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

test('an admin sets up celebrations, keeps a holiday list and turns it on', async ({
  page,
  context,
}) => {
  await signIn(context, 'admin');
  await page.goto('/dashboard/standups');

  await page
    .getByRole('navigation', { name: 'Main navigation' })
    .getByRole('link', { name: 'Celebrations', exact: true })
    .click();
  await expect(page).toHaveURL(/\/dashboard\/celebrations$/);
  await expect(
    page.getByRole('heading', { name: 'Celebrations', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('Celebrations are switched off', { exact: true }),
  ).toBeVisible();

  await chooseOption(page, 'Timezone', 'Asia/Dubai');
  await page.getByRole('checkbox', { name: 'Friday' }).uncheck();
  await page.getByRole('checkbox', { name: 'Sunday' }).check();
  await page.getByRole('button', { name: 'Save settings' }).click();
  await expect(page.getByText('Celebration settings saved')).toBeVisible();

  await page.getByLabel('Date', { exact: true }).fill('2027-12-25');
  await page.getByLabel('Name', { exact: true }).fill('Christmas Day');
  await page.getByRole('button', { name: 'Add holiday' }).click();
  const holidays = page.getByRole('list', { name: 'Holidays' });
  await expect(holidays.getByText('Christmas Day')).toBeVisible();

  await page.getByRole('button', { name: 'Import holidays' }).click();
  await page
    .getByLabel('CSV', { exact: true })
    .fill('date,name\n2027-01-01,New Year\nsoon,Oops\n');
  const preview = page.getByRole('region', { name: 'Holidays in the file' });
  await expect(preview.getByText('Will be saved')).toBeVisible();
  await expect(preview.getByText('Invalid')).toBeVisible();
  await page.getByRole('button', { name: 'Save 1 holiday' }).click();
  await expect(page.getByText('Saved 1 holiday')).toBeVisible();
  await expect(holidays.getByText('New Year')).toBeVisible();

  await page.reload();
  await expect(
    page.getByRole('combobox', { name: 'Timezone', exact: true }),
  ).toHaveText(/Asia\/Dubai/);
  await expect(page.getByRole('checkbox', { name: 'Sunday' })).toBeChecked();
  await expect(
    page.getByRole('checkbox', { name: 'Friday' }),
  ).not.toBeChecked();

  await page.getByRole('button', { name: 'Turn on celebrations' }).click();
  await expect(page.getByText('Celebrations are on')).toBeVisible();
  await expect(
    page.getByText('Celebrations are switched off', { exact: true }),
  ).toHaveCount(0);

  await page.getByRole('button', { name: 'Ask for dates' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByText('2 people will be asked.')).toBeVisible();
  await expect(
    dialog.getByText(/work anniversaries in #general\./),
  ).toBeVisible();
  await dialog.getByRole('button', { name: 'Ask 2 people' }).click();
  await expect(page.getByText('Asking 2 people for their dates')).toBeVisible();
});

test('a Celebrations admin can run it without being a workspace admin', async ({
  page,
  context,
}) => {
  const admin = await context.request.post(
    `${backend}/__test__/session?role=admin`,
  );
  const { csrf_token } = await admin.json();
  const granted = await context.request.put(
    `${backend}/dashboard/api/members/U_LEAD/modules/celebrations`,
    { headers: { 'X-CSRF-Token': csrf_token } },
  );
  expect(granted.ok()).toBe(true);

  await signIn(context, 'feature-admin');
  await page.goto('/dashboard/celebrations');

  await expect(
    page.getByText(
      'Set everything up below, then ask a workspace admin to turn Celebrations on.',
    ),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Turn on celebrations' }),
  ).toHaveCount(0);
  await page.getByRole('checkbox', { name: 'Saturday' }).check();
  await page.getByRole('button', { name: 'Save settings' }).click();
  await expect(page.getByText('Celebration settings saved')).toBeVisible();
});

test('a member sees the settings but cannot change them', async ({
  page,
  context,
}) => {
  await signIn(context, 'member');
  await page.goto('/dashboard/celebrations');

  await expect(
    page.getByRole('heading', { name: 'Celebrations', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('list', { name: 'Holidays' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save settings' })).toHaveCount(
    0,
  );
  await expect(page.getByRole('button', { name: 'Add holiday' })).toHaveCount(
    0,
  );
  await expect(page.getByRole('checkbox', { name: 'Monday' })).toBeDisabled();
});
