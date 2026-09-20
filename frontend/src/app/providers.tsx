import type { ReactNode } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';

import { queryClient } from '@/common/api/query-client';
import { TooltipProvider } from '@/common/components/ui/tooltip';
import { ThemeProvider } from '@/common/providers/theme';
import { useTheme } from '@/common/providers/theme-context';

function Toasts() {
  const { theme } = useTheme();

  return <Toaster theme={theme} richColors closeButton />;
}

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <TooltipProvider>
          {children}
          <Toasts />
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
