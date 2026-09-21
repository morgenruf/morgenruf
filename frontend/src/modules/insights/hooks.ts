import { useQuery } from '@tanstack/react-query';

import { api } from '@/common/api/client';
import { queryKeys } from '@/common/api/query-keys';
import { useMemberDirectory } from '@/common/api/use-member-directory';
import { useSession } from '@/common/auth/use-session';

export function useInsights() {
  const { data: session } = useSession();

  const query = useQuery({
    queryKey: queryKeys.feature(session?.team_id, 'insights', 30),
    queryFn: async ({ signal }) =>
      (await api.insights.getInsights({ days: 30 }, { signal })).data,
  });

  const members = useMemberDirectory();

  return { query, members };
}
