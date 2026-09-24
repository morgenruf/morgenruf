import { queryOptions } from '@tanstack/react-query';

import type { GetReportsParams } from '@/common/api/generated/data-contracts';
import { queryKeys } from '@/common/api/query-keys';
import type { ApplicationServices } from '@/common/api/services';

type QueryServices = Pick<ApplicationServices, 'api'>;

export function reportsOptions(
  { api }: QueryServices,
  team: string | undefined,
  filters: GetReportsParams,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'reports', filters),
    queryFn: async ({ signal }) =>
      (await api.reports.getReports(filters, { signal })).data,
    enabled: !!team,
  });
}
