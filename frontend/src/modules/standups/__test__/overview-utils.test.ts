import { describe, expect, it } from 'vitest';

import {
  nextRunLabel,
  scheduleDays,
  sparklineSegments,
} from '../overview-utils';

describe('standup display helpers', () => {
  it('keeps missing days as sparkline gaps and zero completion as data', () => {
    const segments = sparklineSegments([0, 50, null, 100, null, 20, 30]);
    expect(segments.map((segment) => segment.length)).toEqual([2, 1, 2]);
    expect(segments[0][0].y).toBe(29);
    expect(segments[1][0].y).toBe(3);
    expect(segments[1][0].x).toBeGreaterThan(segments[0][1].x);
    expect(sparklineSegments([null, null])).toEqual([]);
  });

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
