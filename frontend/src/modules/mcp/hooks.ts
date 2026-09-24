import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useServices } from '@/common/api/services-context';
import { useSession } from '@/common/auth/use-session';

import { mcpKeysOptions } from './queries';

export function useMcp() {
  const services = useServices();
  const { api } = services;
  const { data: session } = useSession();
  const key = ['workspace', session?.team_id, 'mcp'];

  const client = useQueryClient();

  const keys = useQuery(mcpKeysOptions(services, session?.team_id));

  const refresh = () => client.invalidateQueries({ queryKey: key });

  const revoke = useMutation({
    mutationFn: (id: number) => api.mcp.revokeKey({ keyId: id }),
    onSuccess: refresh,
  });

  // Return no secret to TanStack's mutation cache; transfer it directly to ephemeral UI state.
  const create = useMutation({
    gcTime: 0,
    mutationFn: async ({
      name,
      receive,
    }: {
      name: string;
      receive: (key: string) => void;
    }) => {
      const response = await api.mcp.createKey({ name });

      receive(response.data.key);
    },
    onSuccess: refresh,
  });

  return { keys, create, revoke, session, canEdit: session?.role === 'admin' };
}
