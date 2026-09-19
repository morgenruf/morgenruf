import type {
  AnalyticsData,
  ParticipationMember,
} from '@/common/api/generated/data-contracts';

export function completionSeries(
  members: ParticipationMember[],
  dates: string[],
) {
  return dates.map((date) => {
    let expected = 0;
    let completed = 0;

    for (const member of members) {
      const day = member.days.find((day) => day.date === date);

      expected += day?.expected ?? 0;
      completed += day?.completed ?? 0;
    }

    return {
      date,
      expected,
      completed,
      rate: expected ? Math.round((completed / expected) * 100) : null,
    };
  });
}

export function analyticsView(
  data: AnalyticsData,
  scheduleId: string,
  includeUnenrolled: boolean,
) {
  const inScope = scheduleId
    ? data.members.filter((member) =>
        member.schedule_ids.includes(Number(scheduleId)),
      )
    : data.members;

  const enrolled = inScope.filter((member) => member.enrolled);
  const unenrolled = inScope.filter((member) => !member.enrolled);

  const selectedSchedule = data.schedules.find(
    (schedule) => String(schedule.schedule_id) === scheduleId,
  );

  const visible = includeUnenrolled ? inScope : enrolled;
  const series = completionSeries(enrolled, data.window_days);

  if (selectedSchedule)
    series.forEach((point, index) => {
      point.rate = selectedSchedule.series[index] ?? null;
    });

  return {
    visible,
    enrolled,
    unenrolled,
    series,
    rate: selectedSchedule?.completion_rate ?? data.completion_rate,
    expected: selectedSchedule?.expected ?? data.expected,
    completed: selectedSchedule?.completed ?? data.completed,
  };
}

export function rateTone(rate: number | null) {
  return rate === null
    ? 'text-muted-foreground'
    : rate >= 70
      ? 'text-success'
      : rate >= 40
        ? 'text-warning'
        : 'text-destructive';
}
