import { queryOptions } from '@tanstack/react-query';

import { queryKeys } from '@/common/api/query-keys';
import type { ApplicationServices } from '@/common/api/services';

type QueryServices = Pick<ApplicationServices, 'api'>;

export function webhooksOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'webhooks', 'list'),
    queryFn: async ({ signal }) =>
      (await api.webhooks.listWebhooks({ signal })).data,
    enabled: !!team,
  });
}

export function webhookEventsOptions(
  { api }: QueryServices,
  team: string | undefined,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'webhooks', 'events'),
    queryFn: async ({ signal }) =>
      (await api.webhooks.getWebhookEvents({ signal })).data,
    enabled: !!team,
  });
}

export function webhookDeliveriesOptions(
  { api }: QueryServices,
  team: string | undefined,
  id: string,
) {
  return queryOptions({
    queryKey: queryKeys.feature(team, 'webhooks', 'deliveries', id),
    queryFn: async ({ signal }) =>
      (
        await api.webhooks.listWebhookDeliveries(
          { hookId: id, limit: 20 },
          { signal },
        )
      ).data,
    enabled: !!team,
  });
}
