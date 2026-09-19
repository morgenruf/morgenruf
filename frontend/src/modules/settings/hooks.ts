import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/common/api/client';
import { useSession } from '@/common/auth/use-session';

export function useSettings() {
  const { data: session } = useSession();

  const standups = useQuery({
    queryKey: ['workspace', session?.team_id, 'standups'],
    queryFn: ({ signal }) =>
      api.standups.listStandups({ signal }).then((r) => r.data),
    enabled: !!session,
  });

  const modules = useQuery({
    queryKey: ['workspace', session?.team_id, 'modules'],
    queryFn: ({ signal }) =>
      api.workspace.listModules({ signal }).then((r) => r.data),
    enabled: !!session,
  });

  return { standups, modules };
}

export function useSettingsMutations() {
  const client = useQueryClient();
  const { data: session } = useSession();

  const invalidate = async () => {
    await Promise.all(
      ['standups', 'settings', 'modules'].map((key) =>
        client.invalidateQueries({
          queryKey: ['workspace', session?.team_id, key],
        }),
      ),
    );
  };

  const module = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      api.workspace.updateModule({ name: name }, { enabled }),
    onSuccess: invalidate,
  });

  const feed = useMutation({
    mutationFn: async (enabled: boolean) => {
      if (enabled) await api.workspace.createFeedToken();
      else await api.workspace.deleteFeedToken();
    },
    onSuccess: invalidate,
  });

  const digest = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number;
      body: Parameters<typeof api.standups.updateStandup>[1];
    }) => api.standups.updateStandup({ standupId: id }, body),
    onSuccess: invalidate,
  });

  return { module, feed, digest };
}
