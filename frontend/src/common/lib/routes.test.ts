import { describe, expect, it } from 'vitest';

import { isLegacyDashboardHash, legacyDashboardPath } from './routes';

describe('legacy dashboard bookmarks', () => {
  it('keeps valid existing section links', () => {
    expect(legacyDashboardPath('#reports')).toBe('/dashboard/reports');
    expect(legacyDashboardPath('#connect')).toBe('/dashboard/connect');
    expect(isLegacyDashboardHash('#settings')).toBe(true);
  });

  it('uses standups for missing and unknown legacy sections', () => {
    expect(legacyDashboardPath('')).toBe('/dashboard/standups');
    expect(legacyDashboardPath('#https://outside.example')).toBe(
      '/dashboard/standups',
    );
    expect(isLegacyDashboardHash('#unknown')).toBe(false);
  });
});
