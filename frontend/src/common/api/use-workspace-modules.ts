import { useQuery } from '@tanstack/react-query';

import { useSession } from '@/common/auth/use-session';

import { api } from './client';
import { queryKeys } from './query-keys';

export function useWorkspaceModules() {
  const { data: session } = useSession();

  return useQuery({
    queryKey: queryKeys.feature(session?.team_id, 'modules'),
    queryFn: async ({ signal }) =>
      (await api.workspace.listModules({ signal })).data,
    enabled: Boolean(session),
  });
}
