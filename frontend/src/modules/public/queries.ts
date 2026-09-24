import { queryOptions } from '@tanstack/react-query';

import type { ApplicationServices } from '@/common/api/services';

export function publicFeedOptions(
  { api }: Pick<ApplicationServices, 'api'>,
  token: string,
) {
  return queryOptions({
    queryKey: ['public-feed', token],
    queryFn: async ({ signal }) =>
      (await api.public.getFeed({ token }, { signal })).data,
    retry: false,
  });
}
