import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/common/api/client';
import { useSession } from '@/common/auth/use-session';

export type WebhookInput = Parameters<typeof api.webhooks.createWebhook>[0];
export type Webhook = Awaited<
  ReturnType<typeof api.webhooks.listWebhooks>
>['data'][number];

export function useWebhooks() {
  const { data: session } = useSession();
  const team = session?.team_id;

  const client = useQueryClient();
  const key = ['workspace', team, 'webhooks'];

  const webhooks = useQuery({
    queryKey: [...key, 'list'],
    enabled: !!team,
    queryFn: async ({ signal }) =>
      (await api.webhooks.listWebhooks({ signal })).data,
  });

  const catalog = useQuery({
    queryKey: [...key, 'events'],
    enabled: !!team,
    queryFn: async ({ signal }) =>
      (await api.webhooks.getWebhookEvents({ signal })).data,
  });

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
  const { data: session } = useSession();

  return useQuery({
    queryKey: ['workspace', session?.team_id, 'webhooks', 'deliveries', id],
    enabled: !!session && open,
    queryFn: async ({ signal }) =>
      (
        await api.webhooks.listWebhookDeliveries(
          { hookId: id, limit: 20 },
          { signal },
        )
      ).data,
  });
}

export function useWebhookTest(id: string) {
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
