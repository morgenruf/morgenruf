import { useQuery } from '@tanstack/react-query';

import { api } from '@/common/api/client';
import { queryKeys } from '@/common/api/query-keys';
import { useSession } from '@/common/auth/use-session';

export function useAnalytics(days: number) {
  const { data: session } = useSession();

  return useQuery({
    queryKey: queryKeys.feature(session?.team_id, 'analytics', days),
    queryFn: async ({ signal }) =>
      (await api.analytics.getAnalytics({ days }, { signal })).data,
  });
}
