import { useQuery } from '@tanstack/react-query';

import { sessionOptions } from '@/common/api/queries';
import { useServices } from '@/common/api/services-context';

export function useSession() {
  return useQuery(sessionOptions(useServices()));
}

export function usePermissions() {
  const { data } = useSession();
  const isAdmin = data?.role === 'admin';

  return {
    isAdmin,
    canAdminister: (module: string) =>
      isAdmin || Boolean(data?.module_admin.includes(module)),
  };
}
