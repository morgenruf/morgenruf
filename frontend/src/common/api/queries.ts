import { queryOptions } from '@tanstack/react-query';

import { queryKeys } from './query-keys';
import type { ApplicationServices } from './services';

type QueryServices = Pick<ApplicationServices, 'api'>;

export function sessionOptions({ api }: QueryServices) {
  return queryOptions({
    queryKey: queryKeys.session,
    queryFn: async ({ signal }) =>
      (await api.session.getSession({ signal })).data,
    staleTime: 60_000,
  });
}

export function modulesOptions({ api }: QueryServices, team?: string) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'modules'),
    queryFn: async ({ signal }) =>
      (await api.workspace.listModules({ signal })).data,
    enabled: !!team,
  });
}

export function channelsOptions({ api }: QueryServices, team?: string) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'channels'),
    queryFn: async ({ signal }) =>
      (await api.workspace.listChannels({ signal })).data,
    enabled: !!team,
  });
}

export function standupsOptions({ api }: QueryServices, team?: string) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'standups'),
    queryFn: async ({ signal }) =>
      (await api.standups.listStandups({ signal })).data,
    enabled: !!team,
  });
}

export function memberDirectoryOptions(
  { api }: QueryServices,
  team?: string,
  channel = '',
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'members', channel),
    queryFn: async ({ signal }) =>
      (
        await api.members.listMembers(channel ? { channel_id: channel } : {}, {
          signal,
        })
      ).data,
    enabled: !!team,
  });
}

export function analyticsOptions(
  { api }: QueryServices,
  team: string | undefined,
  days: number,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'analytics', days),
    queryFn: async ({ signal }) =>
      (await api.analytics.getAnalytics({ days }, { signal })).data,
    enabled: !!team,
  });
}
