import { queryOptions } from '@tanstack/react-query';

import { queryKeys } from '@/common/api/query-keys';
import type { ApplicationServices } from '@/common/api/services';

type QueryServices = Pick<ApplicationServices, 'api'>;

export function standupTemplatesOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'templates'),
    queryFn: async ({ signal }) =>
      (await api.standups.listTemplates({ signal })).data,
    enabled: !!team,
  });
}

// Whether this deployment has an AI provider key. Without one the AI summary
// switch would do nothing, so the editor hides it.
export function aiSummaryOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'ai-summary'),
    queryFn: async ({ signal }) =>
      (await api.standups.getAiSummary({ signal })).data,
    enabled: !!team,
  });
}
