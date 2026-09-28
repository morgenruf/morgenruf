import { describe, expect, it } from 'vitest';

import {
  birthdayLabel,
  isRealBirthday,
  joinedLabel,
  profileFacts,
  profileFormValues,
  profileInput,
} from '../profile';

const record = {
  user_id: 'U1',
  birth_month: 3,
  birth_day: 14,
  start_date: '2023-03-01',
  role: 'Engineer',
  location: 'Berlin',
  ask_me_about: 'Rust',
  celebrate: false,
  updated_by: 'U1',
  updated_at: null,
  set_by_admin: false,
  left_at: null,
};

describe('profile helpers', () => {
  it('labels a birthday without a year', () => {
    expect(birthdayLabel(3, 14)).toBe('14 March');
    expect(birthdayLabel(null, null)).toBe('');
  });

  it('labels a start date by month and year', () => {
    expect(joinedLabel('2023-03-01')).toBe('Joined Mar 2023');
    expect(joinedLabel(null)).toBe('');
  });

  it('accepts 29 February and refuses days a month does not have', () => {
    expect(isRealBirthday('2', '29')).toBe(true);
    expect(isRealBirthday('2', '30')).toBe(false);
    expect(isRealBirthday('4', '31')).toBe(false);
    expect(isRealBirthday('', '31')).toBe(true);
  });

  it('round-trips a stored profile through the form', () => {
    const values = profileFormValues(record);

    expect(values).toMatchObject({
      birth_month: '3',
      birth_day: '14',
      dont_celebrate: true,
    });
    expect(profileInput(values)).toEqual({
      birth_month: 3,
      birth_day: 14,
      start_date: '2023-03-01',
      role: 'Engineer',
      location: 'Berlin',
      ask_me_about: 'Rust',
      celebrate: false,
    });
  });

  it('sends cleared fields as null so the server clears them too', () => {
    expect(
      profileInput({
        ...profileFormValues(record),
        birth_month: '',
        birth_day: '',
        start_date: '',
        role: '   ',
      }),
    ).toMatchObject({
      birth_month: null,
      birth_day: null,
      start_date: null,
      role: null,
    });
  });

  it('summarises a profile for a member card', () => {
    expect(profileFacts(record)).toEqual([
      'Engineer',
      'Birthday 14 March',
      'Joined Mar 2023',
      'Berlin',
    ]);
    expect(profileFacts(undefined)).toEqual([]);
  });
});
