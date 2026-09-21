import type { ReactNode } from 'react';
import { ChevronLeft, LayoutDashboard } from 'lucide-react';
import { Navigate, Outlet, useLocation } from 'react-router';
import { toast } from 'sonner';

import { api, clearSession } from '@/common/api/client';
import { errorMessage } from '@/common/api/errors';
import { useSession } from '@/common/auth/use-session';
import { LoadingTransition } from '@/common/components/loading-transition';
import { ModuleGate } from '@/common/components/module-gate';
import { ErrorState } from '@/common/components/page';
import { ThemeToggle } from '@/common/components/theme-toggle';
import { SidebarProvider } from '@/common/components/ui/sidebar';
import {
  isLegacyDashboardHash,
  legacyDashboardPath,
} from '@/common/lib/routes';

import { AppMain } from './app-main';
import { AppShellSkeleton } from './app-shell-skeleton';
import { AppSidebar, AppSidebarTrigger } from './app-sidebar';

export function AppLayout({
  loadingFallback,
  title,
  pendingView,
}: {
  loadingFallback: ReactNode;
  title: string;
  pendingView?: { title: string; content: ReactNode };
}) {
  const session = useSession();
  const location = useLocation();
  const current = pendingView?.title ?? title;
  const section = location.pathname.split('/')[2];

  const routeModule: Record<string, string> = {
    standups: 'standup',
    today: 'insights',
    automation: 'standup',
    kudos: 'kudos',
    insights: 'insights',
    mcp: 'mcp',
  };

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

  if (isLegacyDashboardHash(location.hash))
    return <Navigate to={legacyDashboardPath(location.hash)} replace />;

  async function logout() {
    try {
      await api.session.logout();
      clearSession();
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
        <AppMain
          key={`${session.data.team_id}:${session.data.user_id}`}
          pathname={location.pathname}
        >
          <LoadingTransition pending={!!pendingView}>
            {pendingView ? (
              pendingView.content
            ) : routeModule[section] ? (
              <ModuleGate
                loadingFallback={loadingFallback}
                module={routeModule[section]}
                label={current}
                requireActive={section !== 'today'}
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
