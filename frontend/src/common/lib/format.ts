/** Shown in place of a value that is missing. Pair it with a screen reader
 * label where it can appear on its own (see EmptyValue). */
export const NO_VALUE = 'n/a';

/** A bare date (2026-09-29) is a calendar day, not UTC midnight. Parsed as
 * UTC it shows the previous day for anyone west of Greenwich. */
function parse(value: string) {
  return new Date(value.length === 10 ? `${value}T00:00:00` : value);
}

export function formatDate(
  value: string | null | undefined,
  options?: Intl.DateTimeFormatOptions,
): string {
  if (!value) return NO_VALUE;

  const date = parse(value);

  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(
        undefined,
        options ?? { day: 'numeric', month: 'short', year: 'numeric' },
      ).format(date);
}

/**
 * A moment in time: the day, the time to the minute and the short zone name,
 * so "14:05" never leaves the reader guessing whose afternoon it is. The year
 * appears only when it is not the current one. Pass a zone to show the time
 * where something runs rather than where the reader is.
 */
export function formatDateTime(
  value: string | null | undefined,
  { timeZone, weekday = false }: { timeZone?: string; weekday?: boolean } = {},
): string {
  if (!value) return NO_VALUE;

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  const options: Intl.DateTimeFormatOptions = {
    ...(weekday ? { weekday: 'short' as const } : {}),
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
    ...(timeZone ? { timeZone } : {}),
  };
  if (date.getFullYear() !== new Date().getFullYear()) options.year = 'numeric';

  try {
    return new Intl.DateTimeFormat(undefined, options).format(date);
  } catch {
    // An unknown zone name: fall back to the reader's own zone.
    delete options.timeZone;
    return new Intl.DateTimeFormat(undefined, options).format(date);
  }
}

/** The time of day only, for lists already grouped under a date. */
export function formatTime(value: string | null | undefined): string {
  return formatDate(value, { hour: '2-digit', minute: '2-digit' });
}

const WEEKDAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const;

/** ["mon", "tue"] reads "Mon, Tue"; Monday to Friday reads "Weekdays". */
export function formatWeekdays(days: readonly string[]): string {
  const chosen = WEEKDAYS.filter((day) =>
    days.some((item) => item.toLowerCase() === day),
  );

  if (chosen.length === 7) return 'Every day';
  if (chosen.length === 5 && !chosen.includes('sat') && !chosen.includes('sun'))
    return 'Weekdays';
  if (!chosen.length) return 'No days';

  return chosen.map((day) => day[0].toUpperCase() + day.slice(1)).join(', ');
}

/** "1 standup", "3 standups". Pass the plural when adding an s is wrong. */
export function plural(
  count: number,
  singular: string,
  pluralForm = `${singular}s`,
): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return 'Never';

  const date = parse(value);
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
