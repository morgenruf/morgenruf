import type { Program, ProgramInput } from './hooks';

export const dayNames = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
];

export function programDefaults(program?: Program): ProgramInput {
  return {
    name: program?.name ?? 'Coffee chats',
    channel_id: program?.channel_id ?? '',
    interval_weeks: program?.interval_weeks ?? 1,
    day_of_week: program?.day_of_week ?? 0,
    hour: program?.hour ?? 10,
    minute: program?.minute ?? 0,
    timezone:
      program?.timezone ??
      Intl.DateTimeFormat().resolvedOptions().timeZone ??
      'UTC',
    enabled: program?.enabled ?? true,
    meeting_minutes:
      program?.meeting_minutes === 15 ||
      program?.meeting_minutes === 45 ||
      program?.meeting_minutes === 60
        ? program.meeting_minutes
        : 30,
    meeting_link: program?.meeting_link ?? '',
    match_working_hours: program?.match_working_hours ?? false,
    suggest_times: program?.suggest_times ?? true,
    use_icebreaker: program?.use_icebreaker ?? true,
    post_stats: program?.post_stats ?? false,
    group_size: program?.group_size ?? 2,
    strict_group_size: program?.strict_group_size ?? false,
    intro_tone:
      program?.intro_tone === 'remote' || program?.intro_tone === 'in_person'
        ? program.intro_tone
        : 'hybrid',
    video_mode:
      program?.video_mode === 'none' || program?.video_mode === 'zoom'
        ? program.video_mode
        : 'link',
    next_round_date: program?.next_round_date?.slice(0, 10) ?? null,
  };
}

export function programTime(program: Pick<ProgramInput, 'hour' | 'minute'>) {
  return `${String(program.hour ?? 10).padStart(2, '0')}:${String(program.minute ?? 0).padStart(2, '0')}`;
}

export function cadenceLabel(program: Program) {
  return `${program.interval_weeks === 1 ? 'Every' : `Every ${program.interval_weeks} weeks on`} ${dayNames[program.day_of_week]} at ${programTime(program)}`;
}

export const attendanceLabels: Record<string, string> = {
  met: 'Met',
  missed: 'Did not meet',
  no_reply: 'No reply',
  undelivered: 'Not delivered',
};

export function attendanceRate(met: number, missed: number) {
  return met + missed ? Math.round((met / (met + missed)) * 100) : null;
}
