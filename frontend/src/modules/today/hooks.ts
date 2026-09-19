import { useQuery } from '@tanstack/react-query';

import { api } from '@/common/api/client';
import { queryKeys } from '@/common/api/query-keys';
import { useSession } from '@/common/auth/use-session';

export function useToday() {
  const { data: session } = useSession();

  return useQuery({
    queryKey: queryKeys.feature(session?.team_id, 'today'),
    queryFn: async ({ signal }) =>
      (await api.insights.getToday({}, { signal })).data,
  });
}
