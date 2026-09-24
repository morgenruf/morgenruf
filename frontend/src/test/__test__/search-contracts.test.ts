import { describe, expect, it } from 'vitest';

import { parseSearch, stringifySearch } from '../../common/routing/search';
import { validateSearch as analytics } from '../../modules/analytics/search';
import { validateSearch as auth } from '../../modules/auth/search';
import { validateSearch as connect } from '../../modules/connect/search';
import { validateSearch as kudos } from '../../modules/kudos/search';
import { validateSearch as members } from '../../modules/members/search';
import { validateSearch as publicSearch } from '../../modules/public/search';
import { validateSearch as reports } from '../../modules/reports/search';
import { validateSearch as standups } from '../../modules/standups/search';

describe('legacy URL search contracts', () => {
  it.each(['true', 'false', '123', '001', '{"a":1}', 'a+b & c'])(
    'preserves literal free text %s',
    (q) => {
      const parsed = parseSearch(stringifySearch({ q }));

      expect(standups.parse(parsed).q).toBe(q);
      expect(members.parse(parsed).q).toBe(q);
    },
  );

  it('uses the first repeated value and does not mutate object prototypes', () => {
    const parsed = parseSearch('?q=first&q=second&__proto__=value');

    expect(parsed.q).toBe('first');
    expect(Object.getPrototypeOf(parsed)).toBe(Object.prototype);
  });

  it('recovers malformed filters and dialog IDs without coercing false to true', () => {
    expect(
      standups.parse({ status: 'other', edit: '-1', new: 'false' }),
    ).toMatchObject({ status: '', edit: '', new: false });
    expect(analytics.parse({ days: '030', unenrolled: 'false' })).toMatchObject(
      { days: 7, unenrolled: false },
    );
    expect(
      members.parse({ role: 'owner', tracking: 'other', sort: 'random' }),
    ).toMatchObject({ role: '', tracking: '', sort: '' });
    expect(kudos.parse({ days: '999' }).days).toBe(30);
    expect(connect.parse({ program: 'invalid' }).program).toBe('');
  });

  it('retains compatible numeric ranges and string IDs', () => {
    expect(analytics.parse({ days: '30', schedule: '01' })).toMatchObject({
      days: 30,
      schedule: '01',
    });
    expect(kudos.parse({ days: '90' }).days).toBe(90);
    expect(standups.parse({ edit: '01', new: 'true' })).toMatchObject({
      edit: '01',
      new: true,
    });
    expect(connect.parse({ program: '01' }).program).toBe('01');
  });

  it('validates calendar dates but leaves reversed valid ranges to the existing form error', () => {
    expect(
      reports.parse({ date_from: '2026-02-30', date_to: 'not-a-date' }),
    ).toMatchObject({ date_from: '', date_to: '' });
    expect(
      reports.parse({ date_from: '2026-09-20', date_to: '2026-09-01' }),
    ).toMatchObject({ date_from: '2026-09-20', date_to: '2026-09-01' });
  });

  it('preserves result precedence and login error state', () => {
    const params = publicSearch.parse(parseSearch('?status=&result=success'));

    expect(params.status ?? params.result ?? 'error').toBe('error');
    expect(
      publicSearch.parse(parseSearch(stringifySearch(params))).status,
    ).toBe('error');
    expect(
      auth.parse(
        parseSearch('?error=invalid-link&next=%2Fdashboard%2Freports'),
      ),
    ).toMatchObject({ error: 'invalid-link', next: '/dashboard/reports' });
  });
});
