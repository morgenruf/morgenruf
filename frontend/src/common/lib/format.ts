export function formatDate(
  value: string | null | undefined,
  options?: Intl.DateTimeFormatOptions,
): string {
  if (!value) return '—';

  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);

  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(
        undefined,
        options ?? { day: 'numeric', month: 'short', year: 'numeric' },
      ).format(date);
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return 'Never';

  // A bare date (2026-09-29) is a calendar day, not UTC midnight. Parsed as
  // UTC it was "Yesterday" by evening in New York for a standup filed today.
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;

  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const startOfDay = new Date(date);
  startOfDay.setHours(0, 0, 0, 0);
  const days = Math.round(
    (startOfToday.getTime() - startOfDay.getTime()) / 86_400_000,
  );

  return days === 0 ? 'Today' : days === 1 ? 'Yesterday' : `${days} days ago`;
}

export function percentage(completed: number, expected: number): string {
  return expected ? `${Math.round((completed / expected) * 100)}%` : '—';
}
