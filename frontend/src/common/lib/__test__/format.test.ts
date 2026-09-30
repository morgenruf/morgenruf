import { afterEach, describe, expect, it, vi } from 'vitest';

import { relativeTime } from '../format';

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
