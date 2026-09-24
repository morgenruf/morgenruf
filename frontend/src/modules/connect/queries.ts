import { queryOptions } from '@tanstack/react-query';

import { queryKeys } from '@/common/api/query-keys';
import type { ApplicationServices } from '@/common/api/services';

type QueryServices = Pick<ApplicationServices, 'api'>;

export function connectProgramsOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'connect', 'programs'),
    queryFn: async ({ signal }) =>
      (await api.connect.listPrograms({ signal })).data,
    enabled: !!team,
  });
}

export function connectZoomOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'connect', 'zoom'),
    queryFn: async ({ signal }) => (await api.connect.getZoom({ signal })).data,
    enabled: !!team,
  });
}

export function connectMembersOptions(
  { api }: QueryServices,
  team: string | undefined,
  id: number,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'connect', id, 'members'),
    queryFn: async ({ signal }) =>
      (await api.connect.listProgramMembers({ programId: id }, { signal }))
        .data,
    enabled: !!team && !!id,
  });
}

export function connectRoundsOptions(
  { api }: QueryServices,
  team: string | undefined,
  id: number,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'connect', id, 'rounds'),
    queryFn: async ({ signal }) =>
      (await api.connect.listRounds({ programId: id }, { signal })).data,
    enabled: !!team && !!id,
  });
}

export function connectParticipationOptions(
  { api }: QueryServices,
  team: string | undefined,
  id: number,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'connect', id, 'participation'),
    queryFn: async ({ signal }) =>
      (
        await api.connect.listParticipation(
          { programId: id, rounds: 6 },
          { signal },
        )
      ).data,
    enabled: !!team && !!id,
  });
}

export function connectMatchesOptions(
  { api }: QueryServices,
  team: string | undefined,
  roundId: number,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'connect', 'matches', roundId),
    queryFn: async ({ signal }) =>
      (await api.connect.listMatches({ roundId }, { signal })).data,
    enabled: !!team && !!roundId,
  });
}
