import { useQuery } from '@tanstack/react-query';

import { useSession } from '@/common/auth/use-session';

import { modulesOptions } from './queries';
import { useServices } from './services-context';

export function useWorkspaceModules() {
  const { data: session } = useSession();

  return useQuery(modulesOptions(useServices(), session?.team_id));
}
