import type { ReactNode } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';

import type { ApplicationServices } from '@/common/api/services';
import { ServicesProvider } from '@/common/api/services-context';
import { TooltipProvider } from '@/common/components/ui/tooltip';
import { ThemeProvider } from '@/common/providers/theme';
import { useTheme } from '@/common/providers/theme-context';

export function Toasts() {
  const { theme } = useTheme();

  return <Toaster theme={theme} richColors closeButton />;
}

export function AppProviders({
  children,
  services,
}: {
  children: ReactNode;
  services: ApplicationServices;
}) {
  return (
    <ServicesProvider services={services}>
      <QueryClientProvider client={services.queryClient}>
        <ThemeProvider>
          <TooltipProvider>{children}</TooltipProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </ServicesProvider>
  );
}
