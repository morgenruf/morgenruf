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

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  const days = Math.floor((Date.now() - date.getTime()) / 86_400_000);

  return days === 0 ? 'Today' : days === 1 ? 'Yesterday' : `${days} days ago`;
}

export function percentage(completed: number, expected: number): string {
  return expected ? `${Math.round((completed / expected) * 100)}%` : '—';
}
