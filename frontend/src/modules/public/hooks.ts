import { useQuery } from '@tanstack/react-query';

import { useServices } from '@/common/api/services-context';

import { publicFeedOptions } from './queries';

export function usePublicFeed(token: string) {
  return useQuery(publicFeedOptions(useServices(), token));
}
