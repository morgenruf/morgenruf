import { describe, expect, it } from 'vitest';

import { answeredSummary } from './today-utils';

describe('Today unscheduled answers', () => {
  it('avoids a zero denominator for weekend or unscheduled submissions', () => {
    expect(
      answeredSummary({ answered: 1, expected: 0, awaiting: 0, blocked: 0 }),
    ).toEqual({
      value: '1',
      description: 'Unscheduled response · Nobody is scheduled today',
    });
  });

  it('keeps the normal response denominator when a standup is scheduled', () => {
    expect(
      answeredSummary({ answered: 3, expected: 4, awaiting: 1, blocked: 0 }),
    ).toEqual({ value: '3 of 4', description: '75% of the team' });
  });
});
