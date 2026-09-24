import { useQuery } from '@tanstack/react-query';

import { useServices } from '@/common/api/services-context';
import { useSession } from '@/common/auth/use-session';

import { todayOptions } from './queries';

export function useToday() {
  const { data: session } = useSession();

  return useQuery(todayOptions(useServices(), session?.team_id));
}
