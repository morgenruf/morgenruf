import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { Api } from '@/common/api/client';
import { useServices } from '@/common/api/services-context';
import { useSession } from '@/common/auth/use-session';

import {
  kudosConfigOptions,
  kudosFeedOptions,
  kudosGiversOptions,
  kudosReceiversOptions,
} from './queries';

export type KudosConfigInput = Parameters<Api['kudos']['updateConfig']>[0];

export function useKudos(days: number) {
  const services = useServices();
  const { api } = services;
  const { data: session } = useSession();
  const team = session?.team_id;

  const client = useQueryClient();
  const key = ['workspace', team, 'kudos'];

  const feed = useQuery(kudosFeedOptions(services, team));
  const receivers = useQuery(kudosReceiversOptions(services, team, days));
  const givers = useQuery(kudosGiversOptions(services, team, days));
  const config = useQuery(kudosConfigOptions(services, team));

  const save = useMutation({
    mutationFn: (data: KudosConfigInput) => api.kudos.updateConfig(data),
    onSuccess: () => client.invalidateQueries({ queryKey: key }),
  });

  return {
    feed,
    receivers,
    givers,
    config,
    save,
    canEdit:
      session?.role === 'admin' || !!session?.module_admin?.includes('kudos'),
  };
}
