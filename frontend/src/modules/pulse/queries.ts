import { queryOptions } from '@tanstack/react-query';

import { queryKeys } from '@/common/api/query-keys';
import type { ApplicationServices } from '@/common/api/services';

type QueryServices = Pick<ApplicationServices, 'api'>;

export function pulseSettingsOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'pulse', 'settings'),
    queryFn: async ({ signal }) =>
      (await api.pulse.getPulseSettings({ signal })).data,
    enabled: !!team,
  });
}

// Rounds under five people come back with their counts only; the page never
// sees a number it could narrow down to one person.
export function pulseTrendOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'pulse', 'trend'),
    queryFn: async ({ signal }) =>
      (await api.pulse.getPulseTrend({ signal })).data,
    enabled: !!team,
  });
}
