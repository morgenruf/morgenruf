import { weekdays } from './form-utils';

export function scheduleDays(days: string[]) {
  if (weekdays.every((day) => days.includes(day))) return 'Every day';
  if (
    days.length === 5 &&
    weekdays.slice(0, 5).every((day) => days.includes(day))
  )
    return 'Mon–Fri';
  return weekdays
    .filter((day) => days.includes(day))
    .map((day) => day[0].toUpperCase() + day.slice(1))
    .join(', ');
}

export function nextRunLabel(value: string, timezone: string) {
  if (!value || Number.isNaN(Date.parse(value))) return null;
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: timezone,
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).format(new Date(value));
  } catch {
    return null;
  }
}
