import { useQuery } from '@tanstack/react-query';

import { analyticsOptions } from '@/common/api/queries';
import { useServices } from '@/common/api/services-context';
import { useSession } from '@/common/auth/use-session';

export function useAnalytics(days: number) {
  const { data: session } = useSession();

  return useQuery(analyticsOptions(useServices(), session?.team_id, days));
}
