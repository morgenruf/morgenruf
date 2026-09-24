import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { Api } from '@/common/api/client';
import { modulesOptions, standupsOptions } from '@/common/api/queries';
import { useServices } from '@/common/api/services-context';
import { useSession } from '@/common/auth/use-session';

export function useSettings() {
  const services = useServices();
  const { data: session } = useSession();

  const standups = useQuery(standupsOptions(services, session?.team_id));
  const modules = useQuery(modulesOptions(services, session?.team_id));

  return { standups, modules };
}

export function useSettingsMutations() {
  const services = useServices();
  const { api } = services;
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

    services.invalidateRouter();
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
      body: Parameters<Api['standups']['updateStandup']>[1];
    }) => api.standups.updateStandup({ standupId: id }, body),
    onSuccess: invalidate,
  });

  return { module, feed, digest };
}
