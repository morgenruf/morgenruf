import { useQuery } from '@tanstack/react-query';

import { useServices } from '@/common/api/services-context';
import { useMemberDirectory } from '@/common/api/use-member-directory';
import { useSession } from '@/common/auth/use-session';

import { insightsOptions } from './queries';

export function useInsights() {
  const { data: session } = useSession();

  const query = useQuery(insightsOptions(useServices(), session?.team_id));
  const members = useMemberDirectory();

  return { query, members };
}
