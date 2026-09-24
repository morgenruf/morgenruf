import { queryOptions } from '@tanstack/react-query';

import { queryKeys } from '@/common/api/query-keys';
import type { ApplicationServices } from '@/common/api/services';

type QueryServices = Pick<ApplicationServices, 'api'>;

export function todayOptions({ api }: QueryServices, team: string | undefined) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'today'),
    queryFn: async ({ signal }) =>
      (await api.insights.getToday({}, { signal })).data,
    enabled: !!team,
  });
}
