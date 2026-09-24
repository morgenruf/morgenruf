import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { Api } from '@/common/api/client';
import { useServices } from '@/common/api/services-context';
import { useSession } from '@/common/auth/use-session';

import {
  webhookDeliveriesOptions,
  webhookEventsOptions,
  webhooksOptions,
} from './queries';

export type WebhookInput = Parameters<Api['webhooks']['createWebhook']>[0];
export type Webhook = Awaited<
  ReturnType<Api['webhooks']['listWebhooks']>
>['data'][number];

export function useWebhooks() {
  const services = useServices();
  const { api } = services;
  const { data: session } = useSession();
  const team = session?.team_id;

  const client = useQueryClient();
  const key = ['workspace', team, 'webhooks'];

  const webhooks = useQuery(webhooksOptions(services, team));
  const catalog = useQuery(webhookEventsOptions(services, team));

  const refresh = () => client.invalidateQueries({ queryKey: key });

  const save = useMutation({
    gcTime: 0,
    mutationFn: async ({
      id,
      data,
      receive,
    }: {
      id?: string;
      data: WebhookInput;
      receive: (secret: string) => void;
    }) => {
      const response = id
        ? await api.webhooks.updateWebhook({ hookId: id }, data)
        : await api.webhooks.createWebhook(data);

      if (response.data.secret) receive(response.data.secret);
    },
    onSuccess: refresh,
  });

  const rotate = useMutation({
    gcTime: 0,
    mutationFn: async ({
      id,
      receive,
    }: {
      id: string;
      receive: (secret: string) => void;
    }) => {
      const response = await api.webhooks.rotateWebhookSecret({ hookId: id });

      if (response.data.secret) receive(response.data.secret);
    },
    onSuccess: refresh,
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.webhooks.deleteWebhook({ hookId: id }),
    onSuccess: refresh,
  });

  return {
    webhooks,
    catalog,
    save,
    rotate,
    remove,
    canEdit: session?.role === 'admin',
  };
}

export function useWebhookDeliveries(id: string, open: boolean) {
  const services = useServices();
  const { data: session } = useSession();

  return useQuery({
    ...webhookDeliveriesOptions(services, session?.team_id, id),
    enabled: !!session && open,
  });
}

export function useWebhookTest(id: string) {
  const services = useServices();
  const { api } = services;
  const { data: session } = useSession();
  const client = useQueryClient();

  return useMutation({
    mutationFn: async () =>
      (await api.webhooks.testWebhook({ hookId: id })).data,
    onSuccess: () =>
      client.invalidateQueries({
        queryKey: ['workspace', session?.team_id, 'webhooks', 'deliveries', id],
      }),
  });
}
