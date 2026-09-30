import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type {
  HolidayImportInput,
  HolidayInput,
  SettingsInput,
} from '@/common/api/generated/data-contracts';
import { channelsOptions, modulesOptions } from '@/common/api/queries';
import { useServices } from '@/common/api/services-context';
import { usePermissions, useSession } from '@/common/auth/use-session';

import {
  celebrationSettingsOptions,
  holidaysOptions,
  upcomingCelebrationsOptions,
} from './queries';

export type CelebrationSettingsInput = SettingsInput;

export function useCelebrationsModule() {
  const services = useServices();
  const { data: session } = useSession();
  const modules = useQuery(modulesOptions(services, session?.team_id));
  const feature = modules.data?.find((item) => item.name === 'celebrations');

  return { modules, feature, active: !!feature?.active };
}

export function useCelebrations() {
  const services = useServices();
  const { api } = services;
  const { data: session } = useSession();
  const team = session?.team_id;
  const { canAdminister, isAdmin } = usePermissions();
  const canEdit = canAdminister('celebrations');

  const client = useQueryClient();
  const key = ['workspace', team, 'celebrations'];
  const invalidate = () => client.invalidateQueries({ queryKey: key });

  const settings = useQuery(celebrationSettingsOptions(services, team));
  const holidays = useQuery(holidaysOptions(services, team));
  const upcoming = useQuery(
    upcomingCelebrationsOptions(services, team, canEdit),
  );
  const channels = useQuery(channelsOptions(services, team));

  const save = useMutation({
    // The form shows this error inline; skip the global toast.
    meta: { silent: true },
    mutationFn: (data: CelebrationSettingsInput) =>
      api.celebrations.updateCelebrationSettings(data),
    onSuccess: invalidate,
  });

  const addHoliday = useMutation({
    // The form shows this error inline; skip the global toast.
    meta: { silent: true },
    mutationFn: (data: HolidayInput) => api.celebrations.addHoliday(data),
    onSuccess: invalidate,
  });

  const removeHoliday = useMutation({
    mutationFn: (day: string) => api.celebrations.deleteHoliday({ day }),
    onSuccess: invalidate,
  });

  const importHolidays = useMutation({
    // The import dialog shows this error inline.
    meta: { silent: true },
    mutationFn: (data: HolidayImportInput) =>
      api.celebrations.importHolidays(data),
    onSuccess: (_response, variables) => {
      if (!variables.preview) void invalidate();
    },
  });

  const enable = useMutation({
    mutationFn: () =>
      api.workspace.updateModule({ name: 'celebrations' }, { enabled: true }),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ['workspace', team, 'modules'] }),
  });

  return {
    settings,
    holidays,
    upcoming,
    channels,
    save,
    addHoliday,
    removeHoliday,
    importHolidays,
    enable,
    canEdit,
    isAdmin,
  };
}
