import { MutationCache, QueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { errorMessage } from './errors';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: false, refetchOnWindowFocus: true },
    mutations: { retry: false, gcTime: 0 },
  },
  mutationCache: new MutationCache({
    onError: (error, _variables, _context, mutation) => {
      if (mutation.meta?.silent !== true) toast.error(errorMessage(error));
    },
  }),
});
