import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/common/api/client';
import { useSession } from '@/common/auth/use-session';

export type KudosConfigInput = Parameters<typeof api.kudos.updateConfig>[0];

export function useKudos(days: number) {
  const { data: session } = useSession();
  const team = session?.team_id;

  const client = useQueryClient();
  const key = ['workspace', team, 'kudos'];

  const feed = useQuery({
    queryKey: [...key, 'feed'],
    enabled: !!team,
    queryFn: async ({ signal }) =>
      (await api.kudos.listKudos({ limit: 50 }, { signal })).data,
  });

  const receivers = useQuery({
    queryKey: [...key, 'receivers', days],
    enabled: !!team,
    queryFn: async ({ signal }) =>
      (await api.kudos.getLeaderboard({ days }, { signal })).data,
  });

  const givers = useQuery({
    queryKey: [...key, 'givers', days],
    enabled: !!team,
    queryFn: async ({ signal }) =>
      (await api.kudos.getGivers({ days }, { signal })).data,
  });

  const config = useQuery({
    queryKey: [...key, 'config'],
    enabled: !!team,
    queryFn: async ({ signal }) => (await api.kudos.getConfig({ signal })).data,
  });

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
