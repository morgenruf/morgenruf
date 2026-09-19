import { useQuery } from '@tanstack/react-query';

import { api } from '@/common/api/client';

export function usePublicFeed(token: string) {
  return useQuery({
    queryKey: ['public-feed', token],
    queryFn: async ({ signal }) =>
      (await api.public.getFeed({ token }, { signal })).data,
    retry: false,
  });
}
