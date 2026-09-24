import { expect, test, type Page } from '@playwright/test';

import { backend } from './environment';

async function expectNoDocumentOverflow(page: Page) {
  expect(
    await page.evaluate(() => ({
      horizontal: document.documentElement.scrollWidth > window.innerWidth,
      vertical: document.documentElement.scrollHeight > window.innerHeight,
      scrollY: window.scrollY,
    })),
  ).toEqual({ horizontal: false, vertical: false, scrollY: 0 });
}

test.beforeEach(async ({ request, context }) => {
  expect((await request.post(`${backend}/__test__/reset`)).ok()).toBe(true);
  expect(
    (await context.request.post(`${backend}/__test__/session?role=admin`)).ok(),
  ).toBe(true);
});

for (const mobile of [false, true]) {
  test(`standup lists and body scroll independently on ${mobile ? 'mobile' : 'desktop'}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: mobile ? 390 : 1280, height: 600 });
    await page.addInitScript(
      (theme) => localStorage.setItem('morgenruf-theme', theme),
      mobile ? 'dark' : 'light',
    );
    await page.route(/\/dashboard\/api\/members(\?.*)?$/, (route) =>
      route.fulfill({
        json: Array.from({ length: 60 }, (_, index) => ({
          id: `U${index}`,
          name: `Participant ${String(index).padStart(2, '0')}`,
          display_name: `person${index}`,
          email: `person${index}@example.com`,
        })),
      }),
    );
    await page.route('**/dashboard/api/templates', (route) =>
      route.fulfill({
        json: Array.from({ length: 24 }, (_, index) => ({
          id: `template-${index}`,
          name: `Template ${index}`,
          description:
            'A set of questions for sharing progress and planning the next day together.',
          questions: [`Question from template ${index}`],
        })),
      }),
    );
    await page.goto('/dashboard/standups?edit=1');

    const dialog = page.getByRole('dialog');
    const header = dialog.locator('[data-slot="dialog-header"]');
    const footer = dialog.locator('[data-slot="dialog-footer"]');
    const body = dialog.locator(
      '[data-slot="dialog-body"] > [data-slot="scroll-area-viewport"]',
    );
    const participants = dialog.getByRole('region', {
      name: 'Participants',
      exact: true,
    });

    await expect(participants.getByRole('checkbox')).toHaveCount(60);

    await page.screenshot({
      path: testInfo.outputPath('participant-search.png'),
      animations: 'disabled',
    });
    await dialog.getByRole('button', { name: 'Use whole channel' }).click();

    await expect(
      footer.getByRole('button', { name: 'Save standup' }),
    ).toBeInViewport();

    await participants.scrollIntoViewIfNeeded();

    const headerBounds = await header.boundingBox();
    const footerBounds = await footer.boundingBox();
    const bodyScroll = await body.evaluate((element) => element.scrollTop);

    await participants.hover();
    await page.mouse.wheel(0, 300);
    await expect
      .poll(() => participants.evaluate((element) => element.scrollTop))
      .toBeGreaterThan(0);

    expect(await body.evaluate((element) => element.scrollTop)).toBe(
      bodyScroll,
    );
    expect(await header.boundingBox()).toEqual(headerBounds);
    expect(await footer.boundingBox()).toEqual(footerBounds);

    await participants.focus();
    await page.keyboard.press('End');

    await expect(
      participants.getByRole('checkbox', { name: 'Participant 59' }),
    ).toBeInViewport();

    await participants
      .getByRole('checkbox', { name: 'Participant 59' })
      .check();
    await page.screenshot({
      path: testInfo.outputPath('participants.png'),
      animations: 'disabled',
    });
    await dialog
      .getByRole('textbox', { name: 'Search participants' })
      .fill('person1@example.com');

    await expect(participants.getByRole('checkbox')).toHaveCount(1);

    await dialog.getByRole('button', { name: 'Select results' }).click();

    await expect(dialog.getByText('2 selected', { exact: true })).toBeVisible();
    await expect(participants.locator('..')).not.toHaveAttribute(
      'data-has-overflow-y',
    );

    await dialog.getByRole('tab', { name: 'Questions' }).click();
    await dialog.getByRole('button', { name: 'Use a template' }).click();

    const templates = dialog.getByRole('region', {
      name: 'Question templates',
    });

    await templates.scrollIntoViewIfNeeded();

    const beforeTemplates = await body.evaluate((element) => element.scrollTop);

    await templates.focus();
    await page.keyboard.press('End');

    await expect(
      templates.getByRole('button', { name: /^Template 23 / }),
    ).toBeInViewport();
    expect(await body.evaluate((element) => element.scrollTop)).toBe(
      beforeTemplates,
    );

    await page.screenshot({
      path: testInfo.outputPath('templates.png'),
      animations: 'disabled',
    });
    await templates.getByRole('button', { name: /^Template 23 / }).click();

    await expect(dialog.getByLabel('Question 1', { exact: true })).toHaveValue(
      'Question from template 23',
    );

    await dialog.getByRole('tab', { name: 'Workspace' }).click();
    await body.focus();
    await page.keyboard.press('End');
    await expect
      .poll(() => body.evaluate((element) => element.scrollTop))
      .toBeGreaterThan(0);

    await expect(
      dialog.getByRole('checkbox', {
        name: 'Enable AI-generated daily summary',
      }),
    ).toBeInViewport();
    await expect(header).toBeInViewport();
    await expect(footer).toBeInViewport();

    await page.screenshot({
      path: testInfo.outputPath('dialog-body.png'),
      animations: 'disabled',
    });
    await expectNoDocumentOverflow(page);
  });
}

test('long select lists keep keyboard navigation and scroll arrows inside the dialog', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 600 });
  await page.route('**/dashboard/api/channels', (route) =>
    route.fulfill({
      json: Array.from({ length: 60 }, (_, index) => ({
        id: index === 0 ? 'C_ENGINEERING' : `C${index}`,
        name: `channel-${String(index).padStart(2, '0')}`,
      })),
    }),
  );
  await page.goto('/dashboard/standups?edit=1');

  const dialog = page.getByRole('dialog');
  const channel = dialog.getByRole('combobox', {
    name: 'Channel',
    exact: true,
  });

  await channel.focus();
  await page.keyboard.press('Space');

  const list = page.getByRole('listbox');

  await expect(list).toBeVisible();
  await expect(
    page.getByRole('option', { name: '#channel-00', exact: true }),
  ).toBeFocused();

  await page.keyboard.press('End');

  const last = page.getByRole('option', { name: '#channel-59', exact: true });

  await expect(last).toBeFocused();
  await expect(last).toBeInViewport();

  await expect
    .poll(() => list.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);
  await page.keyboard.press('Escape');

  await expect(list).toBeHidden();
  await expect(channel).toBeFocused();
  await expect(dialog).toBeVisible();

  await page.keyboard.press('Space');

  await expect(list).toBeVisible();
  await expect(
    page.getByRole('option', { name: '#channel-00', exact: true }),
  ).toBeFocused();

  await page.keyboard.press('End');

  await expect(last).toBeFocused();

  await page.keyboard.press('Enter');

  await expect(channel).toContainText('#channel-59');

  await page.keyboard.press('Space');

  await expect(last).toBeInViewport();
  await expect(
    page.locator('[data-slot="select-scroll-up-button"]'),
  ).toBeVisible();

  await page.keyboard.press('Escape');
  await page.keyboard.press('Escape');

  await expect(dialog).toBeHidden();

  await expectNoDocumentOverflow(page);
});

test('wide content and tab bars use horizontal scroll areas on narrow screens', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 320, height: 600 });
  await page.goto('/dashboard/mcp');

  const configuration = page.getByRole('region', { name: 'MCP configuration' });

  await configuration.scrollIntoViewIfNeeded();
  await expect
    .poll(() =>
      configuration.evaluate(
        (element) => element.scrollWidth > element.clientWidth,
      ),
    )
    .toBe(true);
  await configuration.hover();
  await page.mouse.wheel(250, 0);
  await expect
    .poll(() => configuration.evaluate((element) => element.scrollLeft))
    .toBeGreaterThan(0);
  await page.screenshot({
    path: testInfo.outputPath('horizontal-content.png'),
    animations: 'disabled',
  });
  await expectNoDocumentOverflow(page);

  const main = page.getByRole('main');
  const mainScroll = await main.evaluate((element) => element.scrollTop);

  await configuration.hover();
  await page.mouse.wheel(0, -100);
  await expect
    .poll(() => main.evaluate((element) => element.scrollTop))
    .toBeLessThan(mainScroll);
  await page.goto('/dashboard/connect/attendance');
  await page.getByText('View chart data', { exact: true }).click();

  const chartTable = page.getByRole('table', {
    name: 'Meeting rates and outcomes by round, oldest first',
  });
  const tableViewport = chartTable.locator('..').locator('..');

  await chartTable.scrollIntoViewIfNeeded();
  await tableViewport.hover();
  await page.mouse.wheel(200, 0);
  await expect
    .poll(() => tableViewport.evaluate((element) => element.scrollLeft))
    .toBeGreaterThan(0);
  await expectNoDocumentOverflow(page);
  await page.goto('/dashboard/connect/1');

  const tabs = page.getByRole('tablist', { name: 'Coffee chat settings' });
  const viewport = tabs.locator('..').locator('..');

  await tabs.getByRole('tab').first().focus();
  await page.keyboard.press('ArrowLeft');

  await expect(tabs.getByRole('tab').last()).toBeFocused();
  await expect(tabs.getByRole('tab').last()).toBeInViewport();

  await expect
    .poll(() => viewport.evaluate((element) => element.scrollLeft))
    .toBeGreaterThan(0);
  await expectNoDocumentOverflow(page);
});

test('constrained dropdown menus scroll focused items and restore trigger focus', async ({
  page,
}) => {
  await page.goto('/dashboard/standups');

  // Interact with the settled page header after the bootstrap shell is replaced.
  await expect(
    page.getByRole('button', { name: 'New standup', exact: true }),
  ).toBeVisible();

  await page.addStyleTag({
    content: '[data-slot="dropdown-menu-content"] { max-height: 48px; }',
  });

  const trigger = page.getByRole('button', { name: 'Choose appearance' });

  await trigger.focus();
  await page.keyboard.press('Space');

  const menu = page.getByRole('menu');
  const viewport = menu.locator('[data-slot="scroll-area-viewport"]');

  await expect(
    menu.getByRole('menuitem', { name: 'Light', exact: true }),
  ).toBeFocused();

  await page.keyboard.press('End');

  const last = menu.getByRole('menuitem', { name: 'System', exact: true });

  await expect(last).toBeFocused();
  await expect(last).toBeInViewport();

  await expect
    .poll(() => viewport.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);
  await page.keyboard.press('Escape');

  await expect(menu).toBeHidden();
  await expect(trigger).toBeFocused();
});

test('automation dialog keeps its actions available on a short screen', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 480 });
  await page.goto('/dashboard/automation');
  await page.getByRole('button', { name: 'New rule' }).click();

  const dialog = page.getByRole('dialog');
  const body = dialog.locator(
    '[data-slot="dialog-body"] > [data-slot="scroll-area-viewport"]',
  );
  const header = dialog.locator('[data-slot="dialog-header"]');
  const footer = dialog.locator('[data-slot="dialog-footer"]');

  await dialog.evaluate((element) =>
    Promise.all(element.getAnimations().map((animation) => animation.finished)),
  );

  const headerBounds = await header.boundingBox();
  const footerBounds = await footer.boundingBox();

  await body.focus();
  await page.keyboard.press('End');
  await expect
    .poll(() => body.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);

  expect(await header.boundingBox()).toEqual(headerBounds);
  expect(await footer.boundingBox()).toEqual(footerBounds);
  await expect(
    dialog.getByRole('button', { name: 'Save rule' }),
  ).toBeInViewport();

  await page.screenshot({
    path: testInfo.outputPath('automation-dialog.png'),
    animations: 'disabled',
  });
  await expectNoDocumentOverflow(page);
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();

  await expect(dialog).toBeHidden();
});
