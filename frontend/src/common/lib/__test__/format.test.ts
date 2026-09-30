import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  formatDate,
  formatDateTime,
  formatWeekdays,
  plural,
  relativeTime,
} from '../format';

describe('relativeTime', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('treats a bare date as a local calendar day', () => {
    // 20:45 on 29 September in the local zone. Parsed as UTC midnight, a
    // standup filed that day read as "Yesterday" by the evening in New York.
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 8, 29, 20, 45));

    expect(relativeTime('2026-09-29')).toBe('Today');
    expect(relativeTime('2026-09-28')).toBe('Yesterday');
    expect(relativeTime('2026-09-25')).toBe('4 days ago');
  });

  it('counts calendar days for a full timestamp too', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 8, 29, 0, 30));

    expect(relativeTime(new Date(2026, 8, 28, 23, 50).toISOString())).toBe(
      'Yesterday',
    );
  });

  it('keeps the old answers for missing and unreadable values', () => {
    expect(relativeTime(null)).toBe('Never');
    expect(relativeTime('not a date')).toBe('not a date');
  });
});

describe('formatWeekdays', () => {
  it('orders days, names the common sets and capitalises the rest', () => {
    expect(formatWeekdays(['tue', 'mon'])).toBe('Mon, Tue');
    expect(formatWeekdays(['mon', 'tue', 'wed', 'thu', 'fri'])).toBe(
      'Weekdays',
    );
    expect(
      formatWeekdays(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']),
    ).toBe('Every day');
  });
});

describe('formatDate and formatDateTime', () => {
  it('reads a bare date as the local calendar day', () => {
    expect(formatDate('2026-10-13', { day: 'numeric' })).toBe('13');
  });

  it('shows minutes and a zone name but no seconds', () => {
    const text = formatDateTime('2026-09-21T03:30:05Z', { timeZone: 'UTC' });

    expect(text).toContain('03:30');
    expect(text).toContain('UTC');
    expect(text).not.toContain(':05');
  });

  it('marks a missing value', () => {
    expect(formatDate(null)).toBe('n/a');
    expect(formatDateTime(undefined)).toBe('n/a');
  });
});

describe('plural', () => {
  it('matches the noun to the count', () => {
    expect(plural(1, 'standup')).toBe('1 standup');
    expect(plural(2, 'day')).toBe('2 days');
    expect(plural(0, 'reply', 'replies')).toBe('0 replies');
  });
});
