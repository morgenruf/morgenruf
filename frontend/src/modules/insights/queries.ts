import { queryOptions } from '@tanstack/react-query';

import { queryKeys } from '@/common/api/query-keys';
import type { ApplicationServices } from '@/common/api/services';

type QueryServices = Pick<ApplicationServices, 'api'>;

export function insightsOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'insights', 30),
    queryFn: async ({ signal }) =>
      (await api.insights.getInsights({ days: 30 }, { signal })).data,
    enabled: !!team,
  });
}
