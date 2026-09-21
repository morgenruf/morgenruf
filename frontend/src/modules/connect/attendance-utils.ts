import type { ConnectRound } from '@/common/api/generated/data-contracts';

import { attendanceRate } from './form-utils';

export function attendanceTrend(rounds: readonly ConnectRound[]) {
  return [...rounds]
    .sort(
      (a, b) =>
        (Date.parse(a.scheduled_for) || 0) -
          (Date.parse(b.scheduled_for) || 0) || a.id - b.id,
    )
    .map((round) => ({
      ...round,
      rate: attendanceRate(round.met, round.missed),
    }));
}

export function roundDate(value: string, compact = false) {
  if (!value) return 'Unscheduled';

  return new Date(value).toLocaleDateString(undefined, {
    day: 'numeric',
    month: compact ? 'short' : 'long',
    ...(compact ? {} : { year: 'numeric' }),
  });
}
