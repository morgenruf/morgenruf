import { Link, useLocation } from '@tanstack/react-router';
import {
  BarChart3,
  Cake,
  CalendarCheck,
  Coffee,
  FileChartColumn,
  HeartHandshake,
  Lightbulb,
  ListChecks,
  LogOut,
  MessageCircleHeart,
  MessagesSquare,
  Plug,
  Settings2,
  Sunrise,
  UserRound,
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
  | '/dashboard/polls'
  | '/dashboard/pulse'
  | '/dashboard/celebrations'
  | '/dashboard/watercooler'
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
  // Each feature keeps its own icon colour, Notion style: the label stays
  // neutral and only the glyph is tinted.
  color: string;
  module?: string;
  // Who may open it: a feature's admins, or 'workspace' for workspace admins.
  // Pages that show other people's numbers or the workspace's plumbing are
  // hidden from everyone else; the API refuses them too.
  access?: string;
};

const groups: { label: string; items: NavItem[] }[] = [
  {
    label: '',
    items: [
      {
        label: 'Today',
        path: '/dashboard/today',
        icon: Sunrise,
        color: 'text-orange-500 dark:text-orange-400',
        module: 'insights',
        access: 'standup',
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
        color: 'text-sky-600 dark:text-sky-400',
        module: 'standup',
      },
      {
        label: 'Coffee chats',
        path: '/dashboard/connect',
        icon: Coffee,
        color: 'text-amber-600 dark:text-amber-400',
        module: 'connect',
      },
      {
        label: 'Kudos',
        path: '/dashboard/kudos',
        icon: HeartHandshake,
        color: 'text-rose-500 dark:text-rose-400',
        module: 'kudos',
      },
      {
        label: 'Polls',
        path: '/dashboard/polls',
        icon: ListChecks,
        color: 'text-emerald-600 dark:text-emerald-400',
        module: 'polls',
      },
      {
        label: 'Pulse',
        path: '/dashboard/pulse',
        icon: MessageCircleHeart,
        color: 'text-pink-500 dark:text-pink-400',
        module: 'pulse',
      },
      {
        label: 'Celebrations',
        path: '/dashboard/celebrations',
        icon: Cake,
        color: 'text-violet-500 dark:text-violet-400',
        module: 'celebrations',
      },
      {
        label: 'Watercooler',
        path: '/dashboard/watercooler',
        icon: MessagesSquare,
        color: 'text-amber-600 dark:text-amber-400',
        module: 'watercooler',
        access: 'watercooler',
      },
      {
        label: 'Members',
        path: '/dashboard/members',
        icon: Users,
        color: 'text-teal-600 dark:text-teal-400',
      },
    ],
  },
  {
    label: 'Understand',
    items: [
      {
        label: 'Insights',
        path: '/dashboard/insights',
        icon: Lightbulb,
        color: 'text-yellow-600 dark:text-yellow-400',
        module: 'insights',
        access: 'standup',
      },
      {
        label: 'Reports',
        path: '/dashboard/reports',
        icon: FileChartColumn,
        color: 'text-indigo-500 dark:text-indigo-400',
      },
      {
        label: 'Analytics',
        path: '/dashboard/analytics',
        icon: BarChart3,
        color: 'text-emerald-600 dark:text-emerald-400',
        access: 'standup',
      },
    ],
  },
  {
    label: 'Configure',
    items: [
      {
        label: 'Settings',
        path: '/dashboard/settings',
        icon: Settings2,
        color: 'text-slate-500 dark:text-slate-400',
        access: 'workspace',
      },
      {
        label: 'Automation',
        path: '/dashboard/automation',
        icon: Workflow,
        color: 'text-fuchsia-500 dark:text-fuchsia-400',
        module: 'standup',
        access: 'standup',
      },
      {
        label: 'Webhooks',
        path: '/dashboard/webhooks',
        icon: Webhook,
        color: 'text-cyan-600 dark:text-cyan-400',
        access: 'workspace',
      },
      {
        label: 'MCP',
        path: '/dashboard/mcp',
        icon: Plug,
        color: 'text-lime-600 dark:text-lime-400',
        module: 'mcp',
        access: 'workspace',
      },
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
  const { canAdminister, isAdmin } = usePermissions();
  const mayOpen = (access?: string) =>
    !access || (access === 'workspace' ? isAdmin : canAdminister(access));
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
                mayOpen(item.access) &&
                (!item.module ||
                  !modules.data ||
                  modules.data.find((mod) => mod.name === item.module)
                    ?.available),
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
                          <item.icon className={item.color} />
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
                                    (label !== 'New coffee chat' &&
                                      label !== 'Attendance') ||
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
              render={<Link to="/dashboard/profile" />}
              isActive={isActive('/dashboard/profile')}
              aria-label="My profile"
              tooltip="My profile"
              onClick={closeMobile}
            >
              <UserRound className="text-blue-500 dark:text-blue-400" />
              <span>My profile</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
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
