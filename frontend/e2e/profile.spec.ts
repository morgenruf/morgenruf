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

test('a member fills in their own profile and it survives a reload', async ({
  page,
  context,
}) => {
  await signIn(context, 'member');
  await page.goto('/dashboard/standups');

  await page.getByRole('link', { name: 'My profile' }).click();
  await expect(page).toHaveURL(/\/dashboard\/profile$/);
  await expect(
    page.getByRole('heading', { name: 'My profile', exact: true }),
  ).toBeVisible();

  await chooseOption(page, 'Birthday month', 'February');
  await chooseOption(page, 'Birthday day', '29');
  await page.getByLabel('Started on').fill('2022-05-02');
  await page.getByLabel('Role', { exact: true }).fill('Designer');
  await page.getByRole('button', { name: 'Save profile' }).click();
  await expect(page.getByText('Profile saved')).toBeVisible();

  await page.reload();

  await expect(
    page.getByRole('combobox', { name: 'Birthday day', exact: true }),
  ).toHaveText(/29/);
  await expect(page.getByLabel('Role', { exact: true })).toHaveValue(
    'Designer',
  );
  await expect(page.getByLabel('Started on')).toHaveValue('2022-05-02');
});

test('an admin previews a date import before anything is saved', async ({
  page,
  context,
}) => {
  await signIn(context, 'admin');
  await page.goto('/dashboard/members');

  await expect(
    page.getByText('Engineering lead · Birthday 14 March', { exact: false }),
  ).toBeVisible();

  await page.getByRole('button', { name: 'Import dates' }).click();
  await page
    .getByLabel('CSV')
    .fill(
      'email,birthday,start_date\nu_member@example.test,1990-07-04,2022-05-01\nnobody@example.test,01-01,\n',
    );
  await page.getByRole('button', { name: 'Preview' }).click();

  const preview = page.getByRole('region', { name: 'Rows in the file' });
  await expect(preview.getByText('Will be saved')).toBeVisible();
  await expect(preview.getByText('No member with this email')).toBeVisible();
  await expect(preview.getByText('4 July')).toBeVisible();

  await page.getByRole('button', { name: 'Save 1 member' }).click();
  await expect(page.getByText('Saved dates for 1 member')).toBeVisible();
  await expect(
    page.getByText('Birthday 4 July · Joined May 2022', { exact: false }),
  ).toBeVisible();
});
