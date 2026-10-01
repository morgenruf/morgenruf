import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { channelsOptions } from '@/common/api/queries';
import { useServices } from '@/common/api/services-context';
import { useSession } from '@/common/auth/use-session';

import { pollsOptions } from './queries';

export function usePolls() {
  const services = useServices();
  const { api } = services;
  const { data: session } = useSession();
  const team = session?.team_id;

  const client = useQueryClient();
  const polls = useQuery(pollsOptions(services, team));
  const channels = useQuery(channelsOptions(services, team));

  const close = useMutation({
    // The confirm dialog shows this error inline; skip the global toast.
    meta: { silent: true },
    mutationFn: (pollId: number) => api.polls.closePoll({ pollId }),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ['workspace', team, 'polls'] }),
  });

  return { polls, channels, close };
}
