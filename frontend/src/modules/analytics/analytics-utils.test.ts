import { describe, expect, it } from 'vitest';

import type {
  AnalyticsData,
  ParticipationMember,
} from '@/common/api/generated/data-contracts';

import { analyticsView, completionSeries } from './analytics-utils';

function member(
  user_id: string,
  expected: number,
  completed: number,
  overrides: Partial<ParticipationMember> = {},
): ParticipationMember {
  return {
    user_id,
    real_name: user_id,
    enrolled: true,
    on_vacation: false,
    expected,
    completed,
    missed: expected - completed,
    responses: completed,
    completion_rate: Math.round((completed / Math.max(expected, 1)) * 100),
    last_standup: null,
    days_with_blockers: 0,
    schedules: ['Daily'],
    schedule_ids: [1],
    days: [{ date: '2026-09-01', expected, completed, blocked: false }],
    ...overrides,
  };
}

const data: AnalyticsData = {
  members: [
    member('U1', 10, 0),
    member('U2', 1, 1),
    member('U3', 0, 0, { enrolled: false, schedule_ids: [] }),
  ],
  window_days: ['2026-09-01', '2026-09-02'],
  schedules: [
    {
      schedule_id: 1,
      name: 'Daily',
      expected: 10,
      completed: 4,
      missed: 6,
      completion_rate: 40,
      participants: 2,
      occurrence_days: 1,
      series: [40, null],
    },
  ],
  days: 7,
  expected: 11,
  completed: 1,
  missed: 10,
  completion_rate: 9,
  enrolled_members: 2,
  unenrolled_members: 1,
  on_vacation_members: 0,
};

describe('analytics denominators', () => {
  it('weights expected occurrences rather than averaging member percentages', () => {
    expect(completionSeries(data.members, data.window_days)[0].rate).toBe(9);
  });

  it('leaves unscheduled days empty instead of reporting a failure', () => {
    expect(completionSeries(data.members, data.window_days)[1].rate).toBeNull();
  });

  it('uses authoritative schedule totals and series when filtered', () => {
    const view = analyticsView(data, '1', false);

    expect(view.rate).toBe(40);
    expect(view.expected).toBe(10);
    expect(view.series.map((day) => day.rate)).toEqual([40, null]);
  });

  it('hides unenrolled members by default and preserves them when requested', () => {
    expect(analyticsView(data, '', false).visible).toHaveLength(2);
    expect(analyticsView(data, '', true).visible).toHaveLength(3);
  });
});
