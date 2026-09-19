import { useQuery } from '@tanstack/react-query';

import { api } from '@/common/api/client';
import { queryKeys } from '@/common/api/query-keys';

export function useSession() {
  return useQuery({
    queryKey: queryKeys.session,
    queryFn: async ({ signal }) =>
      (await api.session.getSession({ signal })).data,
    staleTime: 60_000,
  });
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
