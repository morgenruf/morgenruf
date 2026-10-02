import { queryOptions } from '@tanstack/react-query';

import { queryKeys } from '@/common/api/query-keys';
import type { ApplicationServices } from '@/common/api/services';

type QueryServices = Pick<ApplicationServices, 'api'>;

export function watercoolerOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'watercooler', 'overview'),
    queryFn: async ({ signal }) =>
      (await api.watercooler.getWatercooler({ signal })).data,
    enabled: !!team,
  });
}
