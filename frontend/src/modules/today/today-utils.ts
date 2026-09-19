import type { TodayCounts } from '@/common/api/generated/data-contracts';

export function answeredSummary(counts: TodayCounts) {
  if (!counts.expected)
    return {
      value: String(counts.answered),
      description: counts.answered
        ? `${counts.answered === 1 ? 'Unscheduled response' : 'Unscheduled responses'} · Nobody is scheduled today`
        : 'Nobody is scheduled today',
    };

  return {
    value: `${counts.answered} of ${counts.expected}`,
    description: `${Math.round((counts.answered / counts.expected) * 100)}% of the team`,
  };
}
