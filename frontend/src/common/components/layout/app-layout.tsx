import { useState, type ReactNode } from 'react';
import {
  BarChart3,
  CalendarCheck,
  ChevronLeft,
  Coffee,
  FileChartColumn,
  HeartHandshake,
  LayoutDashboard,
  Lightbulb,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Plug,
  Settings2,
  Sunrise,
  Users,
  Webhook,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { Navigate, NavLink, Outlet, useLocation } from 'react-router';
import { toast } from 'sonner';

import { api, clearSession } from '@/common/api/client';
import { errorMessage } from '@/common/api/errors';
import { useWorkspaceModules } from '@/common/api/use-workspace-modules';
import { usePermissions, useSession } from '@/common/auth/use-session';
import { ModuleGate } from '@/common/components/module-gate';
import { ErrorState } from '@/common/components/page';
import { ThemeToggle } from '@/common/components/theme-toggle';
import { Button } from '@/common/components/ui/button';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/common/components/ui/sheet';
import {
  isLegacyDashboardHash,
  legacyDashboardPath,
} from '@/common/lib/routes';
import { cn } from '@/common/lib/utils';

import { AppShellSkeleton } from './app-shell-skeleton';

type NavItem = {
  label: string;
  path: string;
  icon: LucideIcon;
  module?: string;
};

const groups: { label: string; items: NavItem[] }[] = [
  {
    label: '',
    items: [
      { label: 'Today', path: 'today', icon: Sunrise, module: 'insights' },
    ],
  },
  {
    label: 'Run',
    items: [
      {
        label: 'Standups',
        path: 'standups',
        icon: CalendarCheck,
        module: 'standup',
      },
      {
        label: 'Coffee chats',
        path: 'connect',
        icon: Coffee,
        module: 'connect',
      },
      { label: 'Kudos', path: 'kudos', icon: HeartHandshake, module: 'kudos' },
      { label: 'Members', path: 'members', icon: Users },
    ],
  },
  {
    label: 'Understand',
    items: [
      {
        label: 'Insights',
        path: 'insights',
        icon: Lightbulb,
        module: 'insights',
      },
      { label: 'Reports', path: 'reports', icon: FileChartColumn },
      { label: 'Analytics', path: 'analytics', icon: BarChart3 },
    ],
  },
  {
    label: 'Configure',
    items: [
      { label: 'Settings', path: 'settings', icon: Settings2 },
      {
        label: 'Automation',
        path: 'automation',
        icon: Workflow,
        module: 'standup',
      },
      { label: 'Webhooks', path: 'webhooks', icon: Webhook },
      { label: 'MCP', path: 'mcp', icon: Plug, module: 'mcp' },
    ],
  },
];

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
  const modules = useWorkspaceModules();
  const { canAdminister } = usePermissions();

  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

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

  const navigation = (compact = false) => (
    <>
      <NavLink
        to="/dashboard/standups"
        className="flex h-16 items-center gap-2.5 px-3"
        onClick={() => setMobileOpen(false)}
      >
        <img
          src="/static/icon-192.png"
          alt=""
          className="size-8 shrink-0 rounded-md"
        />
        {!compact && (
          <span className="leading-tight">
            <span className="block text-sm font-semibold">Morgenruf</span>
            <span className="text-xs text-muted-foreground">
              Your team's morning call
            </span>
          </span>
        )}
      </NavLink>
      <nav
        aria-label="Main navigation"
        className="flex-1 space-y-4 overflow-y-auto px-2 pb-4"
      >
        {groups.map((group) => {
          const items = group.items.filter(
            (item) =>
              !item.module ||
              !modules.data ||
              modules.data.find((mod) => mod.name === item.module)?.available,
          );

          return items.length ? (
            <div key={group.label}>
              {group.label && !compact && (
                <div className="px-2 pb-1 text-xs font-medium text-muted-foreground">
                  {group.label}
                </div>
              )}
              <div className="space-y-0.5">
                {items.map((item) => (
                  <div key={item.path}>
                    <NavLink
                      to={`/dashboard/${item.path}`}
                      onClick={() => setMobileOpen(false)}
                      title={compact ? item.label : undefined}
                      className={({ isActive }) =>
                        cn(
                          'flex min-h-9 items-center gap-2 rounded-md px-2 text-sm transition-colors hover:bg-sidebar-accent',
                          isActive &&
                            'bg-sidebar-accent font-medium text-sidebar-accent-foreground',
                          compact && 'justify-center',
                        )
                      }
                    >
                      <item.icon className="size-4 shrink-0" />
                      {!compact && <span>{item.label}</span>}
                    </NavLink>
                    {!compact &&
                      item.path === 'connect' &&
                      location.pathname.startsWith('/dashboard/connect') && (
                        <div className="ml-4 mt-1 space-y-0.5 border-l pl-3">
                          {[
                            ['All coffee chats', '/dashboard/connect'],
                            ['New coffee chat', '/dashboard/connect/new'],
                            ['Attendance', '/dashboard/connect/attendance'],
                          ]
                            .filter(
                              ([label]) =>
                                label !== 'New coffee chat' ||
                                canAdminister('connect'),
                            )
                            .map(([label, path]) => (
                              <NavLink
                                end
                                key={path}
                                to={path}
                                onClick={() => setMobileOpen(false)}
                                className={({ isActive }) =>
                                  cn(
                                    'block rounded-md px-2 py-1.5 text-xs text-muted-foreground hover:bg-sidebar-accent',
                                    isActive &&
                                      'bg-sidebar-accent font-medium text-sidebar-accent-foreground',
                                  )
                                }
                              >
                                {label}
                              </NavLink>
                            ))}
                        </div>
                      )}
                  </div>
                ))}
              </div>
            </div>
          ) : null;
        })}
      </nav>
      <div className="border-t p-3">
        <div className="flex items-center gap-2">
          <span className="grid size-8 shrink-0 place-items-center rounded-md bg-primary/10 text-xs font-semibold text-primary">
            {session.data.team_name.slice(0, 2).toUpperCase() || 'M'}
          </span>
          {!compact && (
            <span className="min-w-0 flex-1 truncate text-xs font-medium">
              {session.data.team_name}
            </span>
          )}
          <Button
            variant="ghost"
            size="icon"
            aria-label="Sign out"
            title="Sign out"
            onClick={() => void logout()}
            className={compact ? 'hidden' : ''}
          >
            <LogOut className="size-4" />
          </Button>
        </div>
        {compact && (
          <Button
            variant="ghost"
            size="icon"
            aria-label="Sign out"
            className="mt-2"
            onClick={() => void logout()}
          >
            <LogOut className="size-4" />
          </Button>
        )}
      </div>
    </>
  );

  return (
    <div className="min-h-dvh">
      <a
        href="#main"
        className="sr-only fixed left-4 top-4 z-50 rounded bg-background px-3 py-2 focus:not-sr-only"
      >
        Skip to content
      </a>
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-20 hidden flex-col border-r bg-sidebar md:flex',
          collapsed ? 'w-16' : 'w-60',
        )}
      >
        {navigation(collapsed)}
      </aside>
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent
          side="left"
          className="flex w-72 flex-col gap-0 bg-sidebar p-0"
        >
          <SheetHeader className="sr-only">
            <SheetTitle>Navigation</SheetTitle>
          </SheetHeader>
          {navigation()}
        </SheetContent>
      </Sheet>
      <div
        className={cn(
          'transition-[padding]',
          collapsed ? 'md:pl-16' : 'md:pl-60',
        )}
      >
        <header className="sticky top-0 z-10 flex h-14 items-center gap-3 border-b bg-background/85 px-4 backdrop-blur">
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-label="Open navigation"
            onClick={() => setMobileOpen(true)}
          >
            <Menu className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="hidden md:inline-flex"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            onClick={() => setCollapsed(!collapsed)}
          >
            {collapsed ? (
              <PanelLeftOpen className="size-4" />
            ) : (
              <PanelLeftClose className="size-4" />
            )}
          </Button>
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
        <main
          id="main"
          className="min-w-0"
          key={`${session.data.team_id}:${session.data.user_id}`}
        >
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
        </main>
      </div>
    </div>
  );
}
