import type { Standup, StandupInput } from './hooks';

export const weekdays = [
  'mon',
  'tue',
  'wed',
  'thu',
  'fri',
  'sat',
  'sun',
] as const;

export const defaultQuestions = [
  'What did you complete yesterday?',
  'What are you working on today?',
  'Any blockers?',
];

export const workspaceSettingFields = [
  'edit_window',
  'jira_base_url',
  'github_repo',
  'linear_team',
  'ai_summary_enabled',
  'ai_provider',
] as const;

export function standupDefaults(
  value?: Standup,
  workspace = value,
): StandupInput {
  return {
    name: value?.name ?? 'Morning Standup',
    channel_id: value?.channel_id ?? '',
    schedule_time: value?.schedule_time ?? '09:00',
    schedule_tz:
      value?.schedule_tz ??
      Intl.DateTimeFormat().resolvedOptions().timeZone ??
      'UTC',
    schedule_days: value
      ? value.schedule_days.filter((day): day is (typeof weekdays)[number] =>
          weekdays.includes(day as (typeof weekdays)[number]),
        )
      : weekdays.slice(0, 5),
    questions: value?.questions ?? defaultQuestions,
    participants: value?.participants ?? [],
    active: value?.active ?? true,
    reminder_minutes: value?.reminder_minutes ?? 0,
    report_channel: value?.report_channel ?? '',
    report_time: value?.report_time ?? '',
    digest_email: value?.digest_email ?? '',
    digest_enabled: value?.digest_enabled ?? false,
    nudge_missing: value?.nudge_missing ?? false,
    nudge_minutes_before: value?.nudge_minutes_before ?? 20,
    group_by: value?.group_by ?? 'member',
    post_to_thread: value?.post_to_thread ?? false,
    post_summary: value?.post_summary ?? true,
    notify_on_report: value?.notify_on_report ?? true,
    edit_window:
      workspace?.edit_window === '4h' || workspace?.edit_window === 'none'
        ? workspace.edit_window
        : 'report',
    jira_base_url: workspace?.jira_base_url ?? '',
    github_repo: workspace?.github_repo ?? '',
    linear_team: workspace?.linear_team ?? '',
    ai_summary_enabled: workspace?.ai_summary_enabled ?? false,
    ai_provider:
      workspace?.ai_provider === 'anthropic' ? 'anthropic' : 'openai',
  };
}

export function sortedStandups(items: Standup[]) {
  const minutes = (value: string) => {
    const match = /^(\d{1,2}):(\d{2})/.exec(value);

    return match ? Number(match[1]) * 60 + Number(match[2]) : 1441;
  };

  return [...items].sort(
    (a, b) =>
      minutes(a.schedule_time) - minutes(b.schedule_time) ||
      a.name.localeCompare(b.name),
  );
}

export function healthLabel(rate: number | null | undefined) {
  return rate == null
    ? 'No data yet'
    : rate >= 75
      ? 'Healthy'
      : rate >= 40
        ? 'Slipping'
        : 'Needs a look';
}

export function validTimezone(value: string) {
  try {
    new Intl.DateTimeFormat('en', { timeZone: value }).format();

    return true;
  } catch {
    return false;
  }
}
