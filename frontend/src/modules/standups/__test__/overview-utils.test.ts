import { describe, expect, it } from 'vitest';

import { nextRunLabel, scheduleDays } from '../overview-utils';

describe('standup display helpers', () => {
  it('orders weekdays and summarizes common schedules', () => {
    expect(scheduleDays(['fri', 'mon', 'wed'])).toBe('Mon, Wed, Fri');
    expect(scheduleDays(['mon', 'tue', 'wed', 'thu', 'fri'])).toBe('Mon–Fri');
    expect(
      scheduleDays(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']),
    ).toBe('Every day');
  });

  it('formats the next run in the schedule timezone and handles invalid input', () => {
    expect(nextRunLabel('2026-09-21T03:30:00Z', 'Asia/Kolkata')).toContain(
      '09:00',
    );
    expect(nextRunLabel('2026-09-21T03:30:00Z', 'UTC')).toContain('03:30');
    expect(nextRunLabel('invalid', 'UTC')).toBeNull();
    expect(nextRunLabel('2026-09-21T03:30:00Z', 'invalid')).toBeNull();
  });
});
