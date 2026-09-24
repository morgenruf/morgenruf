import { queryOptions } from '@tanstack/react-query';

import { queryKeys } from '@/common/api/query-keys';
import type { ApplicationServices } from '@/common/api/services';

type QueryServices = Pick<ApplicationServices, 'api'>;

export function mcpKeysOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'mcp'),
    queryFn: async ({ signal }) => (await api.mcp.listKeys({ signal })).data,
    enabled: !!team,
  });
}
