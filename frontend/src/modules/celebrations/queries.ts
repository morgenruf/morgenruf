import { queryOptions } from '@tanstack/react-query';

import { queryKeys } from '@/common/api/query-keys';
import type { ApplicationServices } from '@/common/api/services';

type QueryServices = Pick<ApplicationServices, 'api'>;

export function celebrationSettingsOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'celebrations', 'settings'),
    queryFn: async ({ signal }) =>
      (await api.celebrations.getCelebrationSettings({ signal })).data,
    enabled: !!team,
  });
}

export function holidaysOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'celebrations', 'holidays'),
    queryFn: async ({ signal }) =>
      (await api.celebrations.listHolidays({ signal })).data,
    enabled: !!team,
  });
}

// Lists birthdays, so the endpoint answers admins only and the query is not
// sent for anyone else.
export function upcomingCelebrationsOptions(
  { api }: QueryServices,
  team: string | undefined,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'celebrations', 'upcoming'),
    queryFn: async ({ signal }) =>
      (await api.celebrations.listUpcomingCelebrations({ signal })).data,
    enabled: !!team && enabled,
  });
}
