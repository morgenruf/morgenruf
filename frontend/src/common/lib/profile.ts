import type {
  MemberProfile,
  MemberProfileRecord,
} from '@/common/api/generated/data-contracts';

export const months = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

/** Form state for a profile. Selects hold strings, with '' meaning not set. */
export type ProfileFormValues = {
  birth_month: string;
  birth_day: string;
  start_date: string;
  role: string;
  location: string;
  ask_me_about: string;
  dont_celebrate: boolean;
};

export const profileLimits = { role: 80, location: 80, ask_me_about: 200 };

/** "14 March", or '' when no birthday is on file. */
export function birthdayLabel(
  month: number | null | undefined,
  day: number | null | undefined,
) {
  return month && day ? `${day} ${months[month - 1]}` : '';
}

/** "Joined Mar 2023", or '' when no start date is on file. */
export function joinedLabel(start: string | null | undefined) {
  if (!start) return '';

  const [year, month] = start.split('-').map(Number);

  return year && month ? `Joined ${months[month - 1].slice(0, 3)} ${year}` : '';
}

export function hasDates(profile: MemberProfileRecord | undefined) {
  return !!profile && (!!profile.birth_month || !!profile.start_date);
}

/** The short facts shown on a member card and in the App Home. */
export function profileFacts(profile: MemberProfileRecord | undefined) {
  if (!profile) return [];

  return [
    profile.role,
    birthdayLabel(profile.birth_month, profile.birth_day) &&
      `Birthday ${birthdayLabel(profile.birth_month, profile.birth_day)}`,
    joinedLabel(profile.start_date),
    profile.location,
  ].filter((fact): fact is string => !!fact);
}

export function profileFormValues(
  profile: MemberProfileRecord | undefined,
): ProfileFormValues {
  return {
    birth_month: profile?.birth_month ? String(profile.birth_month) : '',
    birth_day: profile?.birth_day ? String(profile.birth_day) : '',
    start_date: profile?.start_date ?? '',
    role: profile?.role ?? '',
    location: profile?.location ?? '',
    ask_me_about: profile?.ask_me_about ?? '',
    dont_celebrate: profile ? !profile.celebrate : false,
  };
}

/** Everything the form holds, so clearing a field clears it on the server too. */
export function profileInput(values: ProfileFormValues): MemberProfile {
  const text = (value: string) => value.trim() || null;

  return {
    birth_month: values.birth_month ? Number(values.birth_month) : null,
    birth_day: values.birth_day ? Number(values.birth_day) : null,
    start_date: values.start_date || null,
    role: text(values.role),
    location: text(values.location),
    ask_me_about: text(values.ask_me_about),
    celebrate: !values.dont_celebrate,
  };
}

/** Whether a day exists in a month. 29 February counts: leap years have one. */
export function isRealBirthday(month: string, day: string) {
  if (!month || !day) return true;

  return Number(day) <= new Date(2000, Number(month), 0).getDate();
}
