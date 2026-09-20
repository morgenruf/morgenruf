import { expect, test } from '@playwright/test';

import { backend } from './environment';

test.beforeEach(async ({ request, context }) => {
  expect((await request.post(`${backend}/__test__/reset`)).ok()).toBe(true);
  expect(
    (await context.request.post(`${backend}/__test__/session?role=admin`)).ok(),
  ).toBe(true);
});

for (const width of [390, 1440]) {
  for (const theme of ['light', 'dark']) {
    test(`standup overview and editor at ${width}px in ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 850 });
      await page.addInitScript(
        (value) => localStorage.setItem('morgenruf-theme', value),
        theme,
      );
      await page.route('**/dashboard/api/standups', async (route) => {
        const response = await route.fetch();
        const schedules = await response.json();
        await route.fulfill({
          json: [
            schedules[0],
            {
              ...schedules[0],
              id: 2,
              name: 'Infrastructure and developer experience across the distributed platform team',
              schedule_time: '16:30',
              schedule_tz: 'America/Argentina/Buenos_Aires',
              active: false,
              participants: [],
            },
          ],
        });
      });
      await page.goto('/dashboard/standups');
      const list = page.getByRole('list', { name: 'Standup schedules' });
      await expect(list.getByRole('heading')).toHaveCount(2);
      await expect(list.getByText('67%')).toBeVisible();
      await expect(list.getByText('No participation data')).toBeVisible();
      await expect(
        list.getByText('Stats appear after scheduled check-ins.'),
      ).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: testInfo.outputPath('overview.png'),
        animations: 'disabled',
      });
      await list.screenshot({
        path: testInfo.outputPath('participation-rows.png'),
        animations: 'disabled',
      });
      await page
        .getByRole('textbox', { name: 'Search standups' })
        .fill('engineering');
      await page.getByRole('tab', { name: 'Active 1', exact: true }).click();
      await expect(list.getByRole('heading')).toHaveCount(1);
      await page
        .getByRole('button', { name: 'Edit Engineering standup', exact: true })
        .click();
      const dialog = page.getByRole('dialog');
      await dialog.getByRole('tab', { name: 'Questions', exact: true }).click();
      const question = dialog.getByRole('textbox', {
        name: 'Question 1',
        exact: true,
      });
      await question.fill(
        'What did you finish?\nShare a little context for the team.',
      );
      await page.screenshot({
        path: testInfo.outputPath('questions.png'),
        animations: 'disabled',
      });
      await dialog.getByRole('tab', { name: 'Delivery', exact: true }).click();
      await page.screenshot({
        path: testInfo.outputPath('delivery.png'),
        animations: 'disabled',
      });
      await expect(
        dialog.getByRole('button', { name: 'Save standup' }),
      ).toBeInViewport();
      const email = dialog.getByRole('textbox', { name: 'Daily email to' });
      await email.fill('invalid-email');
      await dialog.getByRole('tab', { name: 'Basics' }).click();
      await dialog.getByRole('button', { name: 'Save standup' }).click();
      await expect(email).toBeFocused();
      await expect(
        dialog.getByRole('tab', { name: 'Delivery' }),
      ).toHaveAttribute('aria-selected', 'true');
      await email.clear();
      await dialog.getByRole('tab', { name: 'Questions' }).click();
      await expect(question).toHaveValue(
        'What did you finish?\nShare a little context for the team.',
      );
      await dialog.getByRole('button', { name: 'Cancel' }).click();
      await expect(page).toHaveURL(/q=engineering&status=active$/);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBe(true);
    });
  }
}

test('row menus pause, resume, and confirm deletion using the real API', async ({
  page,
}) => {
  await page.goto('/dashboard/standups');
  const actions = page.getByRole('button', {
    name: 'Actions for Engineering standup',
  });
  await actions.click();
  await page.getByRole('menuitem', { name: 'Pause', exact: true }).click();
  await expect(
    page.getByRole('tab', { name: 'Paused 1', exact: true }),
  ).toBeVisible();
  await actions.click();
  await page.getByRole('menuitem', { name: 'Resume', exact: true }).click();
  await expect(
    page.getByRole('tab', { name: 'Active 1', exact: true }),
  ).toBeVisible();
  await actions.click();
  await page.getByRole('menuitem', { name: 'Delete', exact: true }).click();
  await expect(page.getByRole('alertdialog')).toHaveAccessibleName(
    'Delete Engineering standup?',
  );
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(actions).toBeFocused();
  await actions.click();
  await page.getByRole('menuitem', { name: 'Delete', exact: true }).click();
  await page
    .getByRole('button', { name: 'Delete standup', exact: true })
    .click();
  await expect(page.getByText('Your first standup starts here')).toBeVisible();
});
