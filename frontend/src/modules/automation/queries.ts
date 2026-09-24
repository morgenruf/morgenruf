import { queryOptions } from '@tanstack/react-query';

import { queryKeys } from '@/common/api/query-keys';
import type { ApplicationServices } from '@/common/api/services';

type QueryServices = Pick<ApplicationServices, 'api'>;

export function automationOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'automation'),
    queryFn: async ({ signal }) =>
      (await api.automation.listRules({ signal })).data,
    enabled: !!team,
  });
}
