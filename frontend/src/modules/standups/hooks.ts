import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { Api } from '@/common/api/client';
import {
  analyticsOptions,
  channelsOptions,
  standupsOptions,
} from '@/common/api/queries';
import { useServices } from '@/common/api/services-context';
import { useMemberDirectory } from '@/common/api/use-member-directory';
import { useSession } from '@/common/auth/use-session';

import { standupTemplatesOptions } from './queries';

export type Standup = Awaited<
  ReturnType<Api['standups']['listStandups']>
>['data'][number];
export type StandupInput = Parameters<Api['standups']['createStandup']>[0];

export const standupKeys = {
  list: (workspace?: string) => ['workspace', workspace, 'standups'] as const,
};

export function useStandups() {
  const services = useServices();
  const { data: session } = useSession();

  return useQuery(standupsOptions(services, session?.team_id));
}

export function useStandupResources(channelId = '') {
  const services = useServices();
  const { data: session } = useSession();
  const workspace = session?.team_id;

  const channels = useQuery(channelsOptions(services, workspace));
  const members = useMemberDirectory({ channel: channelId });
  const templates = useQuery(standupTemplatesOptions(services, workspace));

  return { channels, members, templates };
}

export function useStandupHealth() {
  const services = useServices();
  const { data: session } = useSession();

  return useQuery(analyticsOptions(services, session?.team_id, 14));
}

export function useStandupMutations() {
  const services = useServices();
  const { api } = services;
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
