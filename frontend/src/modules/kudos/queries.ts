import { queryOptions } from '@tanstack/react-query';

import { queryKeys } from '@/common/api/query-keys';
import type { ApplicationServices } from '@/common/api/services';

type QueryServices = Pick<ApplicationServices, 'api'>;

export function kudosFeedOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'kudos', 'feed'),
    queryFn: async ({ signal }) =>
      (await api.kudos.listKudos({ limit: 50 }, { signal })).data,
    enabled: !!team,
  });
}

export function kudosReceiversOptions(
  { api }: QueryServices,
  team: string | undefined,
  days: number,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'kudos', 'receivers', days),
    queryFn: async ({ signal }) =>
      (await api.kudos.getLeaderboard({ days }, { signal })).data,
    enabled: !!team,
  });
}

export function kudosGiversOptions(
  { api }: QueryServices,
  team: string | undefined,
  days: number,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'kudos', 'givers', days),
    queryFn: async ({ signal }) =>
      (await api.kudos.getGivers({ days }, { signal })).data,
    enabled: !!team,
  });
}

export function kudosConfigOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'kudos', 'config'),
    queryFn: async ({ signal }) => (await api.kudos.getConfig({ signal })).data,
    enabled: !!team,
  });
}
