import { formatDateTime, formatWeekdays } from '@/common/lib/format';

export function scheduleDays(days: string[]) {
  return formatWeekdays(days);
}

/** When the standup next runs, in its own timezone, or null if unknown. */
export function nextRunLabel(value: string, timezone: string) {
  if (!value || Number.isNaN(Date.parse(value))) return null;
  try {
    new Intl.DateTimeFormat(undefined, { timeZone: timezone });
  } catch {
    return null;
  }
  return formatDateTime(value, { timeZone: timezone, weekday: true });
}
