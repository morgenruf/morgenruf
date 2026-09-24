import { expect, test } from '@playwright/test';

import { backend } from './environment';

test.beforeEach(async ({ request, context }) => {
  expect((await request.post(`${backend}/__test__/reset`)).ok()).toBe(true);
  expect(
    (await context.request.post(`${backend}/__test__/session?role=admin`)).ok(),
  ).toBe(true);
});

for (const mode of ['expanded', 'collapsed', 'mobile']) {
  test(`sidebar scroll area fades and hover scrollbar work when ${mode}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({
      width: mode === 'mobile' ? 390 : 1280,
      height: 440,
    });
    await page.goto('/dashboard/members');

    await expect(
      page.getByRole('textbox', { name: 'Search members' }),
    ).toBeVisible();

    if (mode === 'mobile') {
      await page.getByRole('button', { name: 'Open navigation' }).click();

      await expect(page.getByRole('dialog')).toHaveCSS('opacity', '1');
    } else if (mode === 'collapsed') {
      await page.getByRole('button', { name: 'Collapse sidebar' }).click();

      await expect(page.locator('[data-slot="sidebar-container"]')).toHaveCSS(
        'width',
        '48px',
      );
    }

    const area = page.locator('[data-sidebar="content"]');
    const viewport = area.getByRole('region', { name: 'Sidebar navigation' });
    const scrollbar = area.locator('[data-slot="sidebar-scrollbar"]');
    const thumb = area.locator('[data-slot="sidebar-scroll-thumb"]');
    const fadeOpacity = (edge: 'before' | 'after') =>
      area.evaluate(
        (element, pseudo) => getComputedStyle(element, `::${pseudo}`).opacity,
        edge,
      );

    await expect(area).toHaveAttribute('data-overflow-y-end');
    await expect(area).not.toHaveAttribute('data-overflow-y-start');
    await expect.poll(() => fadeOpacity('before')).toBe('0');
    await expect.poll(() => fadeOpacity('after')).toBe('1');

    await page.mouse.move(mode === 'mobile' ? 380 : 1000, 100);

    await expect(scrollbar).toHaveCSS('opacity', '0');
    await expect(scrollbar).toHaveCSS('pointer-events', 'none');

    await viewport.hover();

    await expect(scrollbar).toHaveCSS('opacity', '1');
    await expect(scrollbar).toHaveCSS('pointer-events', 'auto');

    await page.mouse.wheel(0, 80);

    await expect(area).toHaveAttribute('data-overflow-y-start');
    await expect(area).toHaveAttribute('data-overflow-y-end');
    await expect.poll(() => fadeOpacity('before')).toBe('1');

    await page.screenshot({
      path: testInfo.outputPath(`sidebar-scroll-${mode}.png`),
      animations: 'disabled',
    });

    const handleBounds = await thumb.boundingBox();
    const trackBounds = await scrollbar.boundingBox();

    expect(handleBounds).not.toBeNull();
    expect(trackBounds).not.toBeNull();

    await page.mouse.move(
      handleBounds!.x + handleBounds!.width / 2,
      handleBounds!.y + handleBounds!.height / 2,
    );
    await page.mouse.down();
    await page.mouse.move(
      handleBounds!.x + handleBounds!.width / 2,
      trackBounds!.y + trackBounds!.height,
      { steps: 5 },
    );
    await page.mouse.up();

    await expect(area).not.toHaveAttribute('data-overflow-y-end');
    await expect.poll(() => fadeOpacity('after')).toBe('0');
    await expect(area).toHaveAttribute('data-overflow-y-start');
    await expect(
      page
        .getByRole('navigation', { name: 'Main navigation' })
        .getByRole('link', { name: 'MCP', exact: true }),
    ).toBeInViewport();
    await expect(
      page.getByRole('link', { name: 'Morgenruf', exact: true }),
    ).toBeInViewport();
    await expect(
      page.getByRole('button', { name: 'Sign out' }),
    ).toBeInViewport();

    await viewport.focus();
    await page.keyboard.press('Home');

    await expect(area).not.toHaveAttribute('data-overflow-y-start');
    await expect.poll(() => fadeOpacity('before')).toBe('0');

    await page.mouse.move(mode === 'mobile' ? 380 : 1000, 100);

    await expect(scrollbar).toHaveCSS('opacity', '0');

    await page.setViewportSize({
      width: mode === 'mobile' ? 390 : 1280,
      height: 1000,
    });

    await expect(area).not.toHaveAttribute('data-has-overflow-y');
    await expect(scrollbar).toHaveCount(0);
    await expect.poll(() => fadeOpacity('before')).toBe('0');
    await expect.poll(() => fadeOpacity('after')).toBe('0');
    expect(
      await viewport.evaluate(
        (element) => element.scrollWidth <= element.clientWidth,
      ),
    ).toBe(true);
  });
}
