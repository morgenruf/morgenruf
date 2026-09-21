import { expect, test } from '@playwright/test';

import { backend } from './environment';

test.beforeEach(async ({ request, context }) => {
  expect((await request.post(`${backend}/__test__/reset`)).ok()).toBe(true);
  expect(
    (await context.request.post(`${backend}/__test__/session?role=admin`)).ok(),
  ).toBe(true);
});

for (const mode of ['expanded', 'collapsed', 'mobile']) {
  test(`main content scrolls independently when ${mode}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({
      width: mode === 'mobile' ? 390 : 1280,
      height: 600,
    });
    await page.addInitScript(
      (theme) => localStorage.setItem('morgenruf-theme', theme),
      mode === 'collapsed' ? 'dark' : 'light',
    );
    await page.goto('/dashboard/settings');
    await expect(
      page.getByRole('heading', { name: 'Settings', exact: true }),
    ).toBeVisible();
    await expect(page.locator('[data-loading-skeleton]')).toHaveCount(0);
    if (mode === 'collapsed') {
      await page.getByRole('button', { name: 'Collapse sidebar' }).click();
      await expect(page.locator('[data-slot="sidebar-container"]')).toHaveCSS(
        'width',
        '48px',
      );
    }

    const main = page.getByRole('main');
    const area = page.locator('[data-slot="main-scroll-area"]');
    const scrollbar = area.locator('[data-slot="main-scrollbar"]');
    const header = page.getByRole('banner');
    const headerBounds = await header.boundingBox();

    await expect(main).toHaveCount(1);
    expect(await main.boundingBox()).toMatchObject({ y: 56, height: 544 });
    await expect(area).toHaveAttribute('data-overflow-y-end');
    await header.hover();
    await expect(scrollbar).toHaveCSS('opacity', '0');
    await main.hover();
    await expect(scrollbar).toHaveCSS('opacity', '1');
    await page.mouse.wheel(0, 200);
    await expect(area).toHaveAttribute('data-overflow-y-start');
    expect(await header.boundingBox()).toEqual(headerBounds);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    expect(
      await main.evaluate(
        (element) => element.scrollWidth <= element.clientWidth,
      ),
    ).toBe(true);
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <= window.innerWidth &&
          document.documentElement.scrollHeight <= window.innerHeight,
      ),
    ).toBe(true);
    if (mode !== 'mobile') {
      await expect(
        page.getByRole('button', { name: 'Sign out' }),
      ).toBeInViewport();
      expect(
        await page
          .getByRole('region', { name: 'Sidebar navigation' })
          .evaluate((element) => element.scrollTop),
      ).toBe(0);
    }
    await page.screenshot({
      path: testInfo.outputPath(`main-scroll-${mode}.png`),
      animations: 'disabled',
    });

    await main.focus();
    await page.keyboard.press('End');
    await expect(area).not.toHaveAttribute('data-overflow-y-end');
    await page.keyboard.press('Home');
    await expect(area).not.toHaveAttribute('data-overflow-y-start');
    const scrollFinished = main.evaluate(
      (element) =>
        new Promise<void>((resolve) => {
          element.addEventListener('scrollend', () => resolve(), {
            once: true,
          });
        }),
    );
    await page.keyboard.press('PageDown');
    await scrollFinished;
    await expect(area).toHaveAttribute('data-overflow-y-start');

    await page.getByRole('link', { name: 'Skip to content' }).focus();
    await page.keyboard.press('Enter');
    await expect(main).toBeFocused();
    if (mode === 'mobile') {
      await page.getByRole('button', { name: 'Open navigation' }).click();
    }
    await page
      .getByRole('navigation', { name: 'Main navigation' })
      .getByRole('link', { name: 'Members', exact: true })
      .click();
    await expect(page).toHaveURL(/\/dashboard\/members$/);
    await expect(
      page.getByRole('heading', { name: 'Members', exact: true }),
    ).toBeVisible();
    await expect
      .poll(() => main.evaluate((element) => element.scrollTop))
      .toBe(0);
  });
}
