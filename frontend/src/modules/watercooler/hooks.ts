import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { WatercoolerChannelInput } from '@/common/api/generated/data-contracts';
import { channelsOptions } from '@/common/api/queries';
import { useServices } from '@/common/api/services-context';
import { useSession } from '@/common/auth/use-session';

import { watercoolerOptions } from './queries';

export function useWatercooler() {
  const services = useServices();
  const { api } = services;
  const { data: session } = useSession();
  const team = session?.team_id;

  const client = useQueryClient();
  const overview = useQuery(watercoolerOptions(services, team));
  const channels = useQuery(channelsOptions(services, team));
  const refresh = () =>
    client.invalidateQueries({ queryKey: ['workspace', team, 'watercooler'] });

  const saveChannel = useMutation({
    meta: { silent: true },
    mutationFn: ({
      channelId,
      body,
    }: {
      channelId: string;
      body: WatercoolerChannelInput;
    }) =>
      api.watercooler
        .saveWatercoolerChannel({ channelId }, body)
        .then((r) => r.data),
    onSuccess: refresh,
  });

  const removeChannel = useMutation({
    mutationFn: (channelId: string) =>
      api.watercooler.deleteWatercoolerChannel({ channelId }),
    onSuccess: refresh,
  });

  const postNow = useMutation({
    mutationFn: (channelId: string) =>
      api.watercooler.postWatercoolerNow({ channelId }).then((r) => r.data),
    onSuccess: refresh,
  });

  const addQuestion = useMutation({
    meta: { silent: true },
    mutationFn: (text: string) =>
      api.watercooler.addWatercoolerQuestion({ text }).then((r) => r.data),
    onSuccess: refresh,
  });

  const archiveQuestion = useMutation({
    mutationFn: ({ id, archived }: { id: number; archived: boolean }) =>
      api.watercooler.updateWatercoolerQuestion(
        { questionId: id },
        { archived },
      ),
    onSuccess: refresh,
  });

  const setHidden = useMutation({
    mutationFn: ({ key, hidden }: { key: string; hidden: boolean }) =>
      api.watercooler.setWatercoolerHidden({ key }, { hidden }),
    onSuccess: refresh,
  });

  return {
    overview,
    channels,
    saveChannel,
    removeChannel,
    postNow,
    addQuestion,
    archiveQuestion,
    setHidden,
  };
}
