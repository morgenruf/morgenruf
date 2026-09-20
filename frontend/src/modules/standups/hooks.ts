import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/common/api/client';
import { useMemberDirectory } from '@/common/api/use-member-directory';
import { useSession } from '@/common/auth/use-session';

export type Standup = Awaited<
  ReturnType<typeof api.standups.listStandups>
>['data'][number];
export type StandupInput = Parameters<typeof api.standups.createStandup>[0];

export const standupKeys = {
  list: (workspace?: string) => ['workspace', workspace, 'standups'] as const,
};

export function useStandups() {
  const { data: session } = useSession();

  return useQuery({
    queryKey: standupKeys.list(session?.team_id),
    queryFn: ({ signal }) =>
      api.standups.listStandups({ signal }).then((r) => r.data),
    enabled: !!session,
  });
}

export function useStandupResources(channelId = '') {
  const { data: session } = useSession();
  const workspace = session?.team_id;

  const channels = useQuery({
    queryKey: ['workspace', workspace, 'channels'],
    queryFn: ({ signal }) =>
      api.workspace.listChannels({ signal }).then((r) => r.data),
    enabled: !!workspace,
  });

  const members = useMemberDirectory({ channel: channelId });

  const templates = useQuery({
    queryKey: ['workspace', workspace, 'templates'],
    queryFn: ({ signal }) =>
      api.standups.listTemplates({ signal }).then((r) => r.data),
    enabled: !!workspace,
  });

  return { channels, members, templates };
}

export function useStandupHealth() {
  const { data: session } = useSession();

  return useQuery({
    queryKey: ['workspace', session?.team_id, 'analytics', { days: 14 }],
    queryFn: ({ signal }) =>
      api.analytics.getAnalytics({ days: 14 }, { signal }).then((r) => r.data),
    enabled: !!session,
  });
}

export function useStandupMutations() {
  const client = useQueryClient();
  const { data: session } = useSession();

  const invalidate = async () => {
    await Promise.all(
      ['standups', 'settings', 'members', 'analytics', 'stats', 'today'].map(
        (key) =>
          client.invalidateQueries({
            queryKey: ['workspace', session?.team_id, key],
          }),
      ),
    );
  };

  const save = useMutation({
    mutationFn: ({ id, body }: { id?: number; body: StandupInput }) =>
      id
        ? api.standups
            .updateStandup({ standupId: id }, body)
            .then((r) => r.data)
        : api.standups.createStandup(body).then((r) => r.data),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.standups.deleteStandup({ standupId: id }),
    onSuccess: invalidate,
  });

  return { save, remove };
}
