import { expect, test } from '@playwright/test';

import { backend } from './environment';

test.beforeEach(async ({ request, context, page }) => {
  expect((await request.post(`${backend}/__test__/reset`)).ok()).toBe(true);
  expect(
    (await context.request.post(`${backend}/__test__/session?role=admin`)).ok(),
  ).toBe(true);
  await page.route(/\/dashboard\/api\/analytics(?:\?|$)/, async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.schedules[0].series = data.window_days.map(
      (_: string, i: number) => [0, 39, 40, null, 69, 70, 100][i % 7],
    );
    await route.fulfill({ json: data });
  });
});

test('analytics charts follow the time range and standup filters', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/dashboard/analytics?schedule=1');
  const trend = page.getByRole('group', {
    name: 'Engineering standup daily completion trend',
  });
  await expect(trend.locator('linearGradient[id$="-point"]')).toHaveCount(7);
  await page.getByRole('tab', { name: '30 days' }).click();
  await expect(trend.locator('linearGradient[id$="-point"]')).toHaveCount(30);
  await expect(page).toHaveURL(/days=30/);
  await page.getByText('View chart data', { exact: true }).click();
  const data = page.locator('details').getByRole('table');
  await expect(data.getByRole('row')).toHaveCount(31);
  await page.getByRole('combobox', { name: 'Standup', exact: true }).click();
  await page.getByRole('option', { name: 'All standups', exact: true }).click();
  await expect(
    data.getByRole('cell', { name: '67%', exact: true }),
  ).toHaveCount(30);
  await expect(
    data.getByRole('cell', { name: 'Not scheduled', exact: true }),
  ).toHaveCount(0);
});

for (const width of [390, 1440]) {
  for (const theme of ['light', 'dark']) {
    for (const reducedMotion of ['reduce', 'no-preference'] as const) {
      test(`charts at ${width}px in ${theme}, motion ${reducedMotion}`, async ({
        page,
      }, testInfo) => {
        const errors: string[] = [];
        page.on('pageerror', (error) => errors.push(error.message));
        await page.setViewportSize({ width, height: 900 });
        await page.emulateMedia({ reducedMotion });
        await page.addInitScript(
          (value) => localStorage.setItem('morgenruf-theme', value),
          theme,
        );
        await page.goto('/dashboard/analytics?schedule=1');
        const completion = page.getByRole('group', {
          name: /Completion percentage by day/,
        });
        await expect(completion.locator('.recharts-area-curve')).toBeVisible();
        await expect(
          completion.locator('.recharts-cartesian-axis-tick-value').first(),
        ).toHaveAttribute('fill', 'var(--muted-foreground)');
        await expect(completion.getByText('0%', { exact: true })).toBeVisible();
        await expect(
          completion.getByText('100%', { exact: true }),
        ).toBeVisible();
        await completion.getByRole('application').focus();
        await expect(page.locator('[data-chart-tooltip]')).toContainText('0%');
        if (reducedMotion === 'reduce') {
          await expect(
            completion.locator('mask[id$="-reveal-mask"]'),
          ).toHaveCount(0);
          const transition = await completion
            .locator('.recharts-tooltip-wrapper')
            .evaluate((node) => getComputedStyle(node).transitionDuration);
          expect(Number.parseFloat(transition)).toBeLessThan(0.001);
        } else {
          await expect(
            completion.locator('mask[id$="-reveal-mask"]'),
          ).toHaveCount(1);
          await expect
            .poll(() =>
              completion
                .locator('mask[id$="-reveal-mask"] rect')
                .evaluateAll((nodes) =>
                  nodes.every((node) =>
                    ['none', 'matrix(1, 0, 0, 1, 0, 0)'].includes(
                      getComputedStyle(node).transform,
                    ),
                  ),
                ),
            )
            .toBe(true);
        }
        await page.keyboard.press('Escape');
        await completion.screenshot({
          path: testInfo.outputPath('completion.png'),
        });
        await page.getByText('View chart data', { exact: true }).click();
        await expect(
          page.getByRole('cell', { name: 'Not scheduled', exact: true }),
        ).toBeVisible();

        const trend = page.getByRole('group', {
          name: 'Engineering standup daily completion trend',
        });
        await trend.scrollIntoViewIfNeeded();
        await trend.getByRole('application').focus();
        for (let i = 0; i < 3; i++) await page.keyboard.press('ArrowRight');
        const tooltip = page.locator('[data-chart-tooltip]:visible');
        await expect(tooltip).toContainText('Not scheduled');
        await expect(tooltip).toBeInViewport();
        expect(
          await tooltip.evaluate(
            (node) => node.closest('[data-slot="table-container"]') === null,
          ),
        ).toBe(true);
        if (reducedMotion === 'no-preference') {
          const bars = trend.locator('.recharts-bar-rectangle g');
          await expect
            .poll(() =>
              bars.evaluateAll((nodes) =>
                nodes.every((node) =>
                  ['none', 'matrix(1, 0, 0, 1, 0, 0)'].includes(
                    getComputedStyle(node).transform,
                  ),
                ),
              ),
            )
            .toBe(true);
          await trend.hover();
          expect(
            await bars.evaluateAll((nodes) =>
              nodes.every((node) =>
                ['none', 'matrix(1, 0, 0, 1, 0, 0)'].includes(
                  getComputedStyle(node).transform,
                ),
              ),
            ),
          ).toBe(true);
        }
        await page.screenshot({ path: testInfo.outputPath('daily-trend.png') });
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth,
          ),
        ).toBe(true);

        await page.goto('/dashboard/standups');
        const sparkline = page
          .getByRole('list', { name: 'Standup schedules' })
          .locator('[data-slot="chart"]');
        await expect(sparkline.locator('.recharts-line-curve')).toBeVisible();
        await expect(sparkline.locator('[role="application"]')).toHaveCount(0);
        const box = await sparkline.boundingBox();
        expect(box?.width).toBe(80);
        expect(box?.height).toBe(28);
        await page.screenshot({
          path: testInfo.outputPath('standup-sparkline.png'),
          animations: 'disabled',
        });

        await page.goto('/dashboard/connect/attendance');
        const attendance = page.getByRole('group', {
          name: /Meeting rate by round, from 0 to 100 percent/,
        });
        await attendance.scrollIntoViewIfNeeded();
        await expect(
          attendance.locator('.recharts-line-dots [data-chart-dot]'),
        ).toHaveCount(1);
        await attendance.getByRole('application').focus();
        await page.keyboard.press('ArrowRight');
        await expect(page.locator('[data-chart-tooltip]')).toContainText(
          'Meeting rate: 100%',
        );
        await expect(page.locator('[data-chart-tooltip]')).toContainText('Met');
        await expect(page.locator('[data-chart-tooltip]')).toContainText(
          'No reply',
        );
        await attendance.screenshot({
          path: testInfo.outputPath('attendance.png'),
          animations: 'disabled',
        });
        await page.getByText('View chart data', { exact: true }).click();
        await expect(
          page.getByRole('table', {
            name: 'Meeting rates and outcomes by round, oldest first',
          }),
        ).toBeVisible();
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth,
          ),
        ).toBe(true);
        expect(errors).toEqual([]);
      });
    }
  }
}
