import type { ReactNode } from 'react';
import { Navigate, Outlet, useLocation } from '@tanstack/react-router';
import { ChevronLeft, LayoutDashboard } from 'lucide-react';
import { toast } from 'sonner';

import { errorMessage } from '@/common/api/errors';
import { useServices, useSessionIdentity } from '@/common/api/services-context';
import { useSession } from '@/common/auth/use-session';
import { LoadingTransition } from '@/common/components/loading-transition';
import { ModuleGate } from '@/common/components/module-gate';
import { ErrorState } from '@/common/components/page';
import { ThemeToggle } from '@/common/components/theme-toggle';
import { SidebarProvider } from '@/common/components/ui/sidebar';
import type { DashboardRouteMetadata } from '@/common/routing/metadata';

import { AppMain } from './app-main';
import { AppShellSkeleton } from './app-shell-skeleton';
import { AppSidebar, AppSidebarTrigger } from './app-sidebar';

export function AppLayout({
  loadingFallback,
  title,
  pendingView,
  requirement,
}: {
  loadingFallback: ReactNode;
  title: string;
  pendingView?: { title: string; content: ReactNode };
  requirement: DashboardRouteMetadata;
}) {
  const session = useSession();
  const services = useServices();
  const identity = useSessionIdentity();
  const location = useLocation();
  const current = pendingView?.title ?? title;

  if (session.isPending)
    return <AppShellSkeleton>{loadingFallback}</AppShellSkeleton>;

  if (session.error)
    return (
      <div className="page">
        <ErrorState
          error={session.error}
          retry={() => void session.refetch()}
        />
      </div>
    );

  if (!session.data) return <Navigate to="/dashboard/login" replace />;

  async function logout() {
    try {
      await services.api.session.logout();
      services.clearSession();
      window.location.assign('/dashboard/login');
    } catch (error) {
      toast.error(errorMessage(error));
    }
  }

  return (
    <SidebarProvider className="h-dvh min-h-0 overflow-hidden">
      <a
        href="#main"
        className="sr-only fixed left-4 top-4 z-50 rounded bg-background px-3 py-2 focus:not-sr-only"
      >
        Skip to content
      </a>

      <AppSidebar
        teamName={session.data.team_name}
        onLogout={() => void logout()}
      />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="relative z-10 flex h-14 shrink-0 items-center gap-3 border-b bg-background/85 px-4 backdrop-blur">
          <AppSidebarTrigger />
          <nav
            aria-label="Breadcrumb"
            className="flex min-w-0 items-center gap-2 text-sm"
          >
            <LayoutDashboard className="size-3.5 shrink-0 text-muted-foreground" />
            <ChevronLeft className="size-3 rotate-180 text-muted-foreground" />
            <span aria-current="page" className="truncate">
              {current}
            </span>
          </nav>
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </header>

        <AppMain key={identity} pathname={location.pathname}>
          <LoadingTransition pending={!!pendingView}>
            {pendingView ? (
              pendingView.content
            ) : requirement.module && !requirement.customGate ? (
              <ModuleGate
                loadingFallback={loadingFallback}
                module={requirement.module}
                label={current}
                requireActive={requirement.requireActive}
              >
                <Outlet />
              </ModuleGate>
            ) : (
              <Outlet />
            )}
          </LoadingTransition>
        </AppMain>
      </div>
    </SidebarProvider>
  );
}
