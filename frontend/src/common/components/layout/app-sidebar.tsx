import { Link, useLocation } from '@tanstack/react-router';
import {
  BarChart3,
  CalendarCheck,
  Coffee,
  FileChartColumn,
  HeartHandshake,
  Lightbulb,
  LogOut,
  Plug,
  Settings2,
  Sunrise,
  Users,
  Webhook,
  Workflow,
  X,
  type LucideIcon,
} from 'lucide-react';

import { useWorkspaceModules } from '@/common/api/use-workspace-modules';
import { usePermissions } from '@/common/auth/use-session';
import { Button } from '@/common/components/ui/button';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarTrigger,
  useSidebar,
} from '@/common/components/ui/sidebar';

type DashboardPath =
  | '/dashboard/today'
  | '/dashboard/standups'
  | '/dashboard/connect'
  | '/dashboard/kudos'
  | '/dashboard/members'
  | '/dashboard/insights'
  | '/dashboard/reports'
  | '/dashboard/analytics'
  | '/dashboard/settings'
  | '/dashboard/automation'
  | '/dashboard/webhooks'
  | '/dashboard/mcp';

type NavItem = {
  label: string;
  path: DashboardPath;
  icon: LucideIcon;
  module?: string;
};

const groups: { label: string; items: NavItem[] }[] = [
  {
    label: '',
    items: [
      {
        label: 'Today',
        path: '/dashboard/today',
        icon: Sunrise,
        module: 'insights',
      },
    ],
  },
  {
    label: 'Run',
    items: [
      {
        label: 'Standups',
        path: '/dashboard/standups',
        icon: CalendarCheck,
        module: 'standup',
      },
      {
        label: 'Coffee chats',
        path: '/dashboard/connect',
        icon: Coffee,
        module: 'connect',
      },
      {
        label: 'Kudos',
        path: '/dashboard/kudos',
        icon: HeartHandshake,
        module: 'kudos',
      },
      { label: 'Members', path: '/dashboard/members', icon: Users },
    ],
  },
  {
    label: 'Understand',
    items: [
      {
        label: 'Insights',
        path: '/dashboard/insights',
        icon: Lightbulb,
        module: 'insights',
      },
      { label: 'Reports', path: '/dashboard/reports', icon: FileChartColumn },
      { label: 'Analytics', path: '/dashboard/analytics', icon: BarChart3 },
    ],
  },
  {
    label: 'Configure',
    items: [
      { label: 'Settings', path: '/dashboard/settings', icon: Settings2 },
      {
        label: 'Automation',
        path: '/dashboard/automation',
        icon: Workflow,
        module: 'standup',
      },
      { label: 'Webhooks', path: '/dashboard/webhooks', icon: Webhook },
      { label: 'MCP', path: '/dashboard/mcp', icon: Plug, module: 'mcp' },
    ],
  },
];

export function AppSidebar({
  teamName,
  onLogout,
}: {
  teamName: string;
  onLogout: () => void;
}) {
  const modules = useWorkspaceModules();
  const { canAdminister } = usePermissions();
  const { pathname } = useLocation();
  const { isMobile, setOpenMobile } = useSidebar();

  const closeMobile = () => setOpenMobile(false);
  const isActive = (path: string, end = false) =>
    pathname === path || (!end && pathname.startsWith(`${path}/`));

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <div className="flex items-center gap-2">
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                size="lg"
                render={<Link to="/dashboard/standups" />}
                aria-label="Morgenruf"
                tooltip="Morgenruf"
                onClick={closeMobile}
              >
                <img
                  src="/static/icon-192.png"
                  alt=""
                  className="size-8 shrink-0 rounded-md"
                />
                <span className="grid min-w-0 flex-1 text-left leading-tight group-data-[collapsible=icon]:hidden">
                  <span className="truncate font-semibold">Morgenruf</span>
                  <span className="truncate text-muted-foreground">
                    Your team's morning call
                  </span>
                </span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
          {isMobile && (
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Close navigation"
              onClick={closeMobile}
            >
              <X />
            </Button>
          )}
        </div>
      </SidebarHeader>

      <SidebarContent>
        <nav aria-label="Main navigation">
          {groups.map((group) => {
            const items = group.items.filter(
              (item) =>
                !item.module ||
                !modules.data ||
                modules.data.find((mod) => mod.name === item.module)?.available,
            );

            return items.length ? (
              <SidebarGroup key={group.label}>
                {group.label && (
                  <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
                )}
                <SidebarGroupContent>
                  <SidebarMenu>
                    {items.map((item) => (
                      <SidebarMenuItem key={item.path}>
                        <SidebarMenuButton
                          render={<Link to={item.path} />}
                          isActive={isActive(item.path)}
                          aria-label={item.label}
                          tooltip={item.label}
                          onClick={closeMobile}
                        >
                          <item.icon />
                          <span>{item.label}</span>
                        </SidebarMenuButton>
                        {item.path === '/dashboard/connect' &&
                          isActive('/dashboard/connect') && (
                            <SidebarMenuSub>
                              {(
                                [
                                  ['All coffee chats', '/dashboard/connect'],
                                  ['New coffee chat', '/dashboard/connect/new'],
                                  [
                                    'Attendance',
                                    '/dashboard/connect/attendance',
                                  ],
                                ] as const
                              )
                                .filter(
                                  ([label]) =>
                                    label !== 'New coffee chat' ||
                                    canAdminister('connect'),
                                )
                                .map(([label, path]) => (
                                  <SidebarMenuSubItem key={path}>
                                    <SidebarMenuSubButton
                                      render={
                                        <Link
                                          to={path}
                                          activeOptions={{ exact: true }}
                                        />
                                      }
                                      isActive={isActive(path, true)}
                                      onClick={closeMobile}
                                    >
                                      <span>{label}</span>
                                    </SidebarMenuSubButton>
                                  </SidebarMenuSubItem>
                                ))}
                            </SidebarMenuSub>
                          )}
                      </SidebarMenuItem>
                    ))}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            ) : null;
          })}
        </nav>
      </SidebarContent>

      <SidebarGroup className="shrink-0 py-2">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={onLogout}
              aria-label="Sign out"
              tooltip="Sign out"
            >
              <LogOut />
              <span>Sign out</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>

      <SidebarFooter className="border-t">
        <div className="flex min-w-0 items-center gap-2" title={teamName}>
          <span
            className="grid size-8 shrink-0 place-items-center rounded-md bg-sidebar-primary/10 text-xs font-semibold text-sidebar-primary"
            aria-hidden="true"
          >
            {teamName.slice(0, 2).toUpperCase() || 'M'}
          </span>
          <span className="truncate text-xs font-medium group-data-[collapsible=icon]:sr-only">
            {teamName}
          </span>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}

export function AppSidebarTrigger() {
  const { isMobile, open, openMobile } = useSidebar();

  return (
    <SidebarTrigger
      aria-label={
        isMobile
          ? 'Open navigation'
          : open
            ? 'Collapse sidebar'
            : 'Expand sidebar'
      }
      aria-expanded={isMobile ? openMobile : open}
    />
  );
}
