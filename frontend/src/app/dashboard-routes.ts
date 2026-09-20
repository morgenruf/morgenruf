import type { ComponentType } from 'react';
import { redirect, type RouteObject } from 'react-router';

import { legacyDashboardPath } from '@/common/lib/routes';
import { AnalyticsPageSkeleton } from '@/modules/analytics/loading';
import { AutomationPageSkeleton } from '@/modules/automation/loading';
import {
  ConnectAttendancePageSkeleton,
  ConnectDetailPageSkeleton,
  ConnectListPageSkeleton,
  ConnectNewPageSkeleton,
} from '@/modules/connect/loading';
import { InsightsPageSkeleton } from '@/modules/insights/loading';
import { KudosPageSkeleton } from '@/modules/kudos/loading';
import { McpPageSkeleton } from '@/modules/mcp/loading';
import { MembersPageSkeleton } from '@/modules/members/loading';
import { ReportsPageSkeleton } from '@/modules/reports/loading';
import { SettingsPageSkeleton } from '@/modules/settings/loading';
import { StandupsPageSkeleton } from '@/modules/standups/loading';
import { TodayPageSkeleton } from '@/modules/today/loading';
import { WebhooksPageSkeleton } from '@/modules/webhooks/loading';

export type LoadingRouteHandle = { title: string; Skeleton: ComponentType };

export const dashboardRoutes: RouteObject[] = [
  {
    index: true,
    loader: () => redirect(legacyDashboardPath(window.location.hash)),
  },
  {
    path: 'today',
    handle: {
      title: 'Today',
      Skeleton: TodayPageSkeleton,
    } satisfies LoadingRouteHandle,
    lazy: async () => ({
      Component: (await import('@/modules/today/pages/today-page')).default,
    }),
  },
  {
    path: 'standups',
    handle: {
      title: 'Standups',
      Skeleton: StandupsPageSkeleton,
    } satisfies LoadingRouteHandle,
    lazy: async () => ({
      Component: (await import('@/modules/standups/pages')).StandupsPage,
    }),
  },
  {
    path: 'connect',
    handle: {
      title: 'Coffee chats',
      Skeleton: ConnectListPageSkeleton,
    } satisfies LoadingRouteHandle,
    lazy: async () => ({
      Component: (await import('@/modules/connect/pages')).ConnectListPage,
    }),
  },
  {
    path: 'connect/new',
    handle: {
      title: 'New coffee chat',
      Skeleton: ConnectNewPageSkeleton,
    } satisfies LoadingRouteHandle,
    lazy: async () => ({
      Component: (await import('@/modules/connect/pages')).ConnectNewPage,
    }),
  },
  {
    path: 'connect/attendance',
    handle: {
      title: 'Attendance',
      Skeleton: ConnectAttendancePageSkeleton,
    } satisfies LoadingRouteHandle,
    lazy: async () => ({
      Component: (await import('@/modules/connect/pages'))
        .ConnectAttendancePage,
    }),
  },
  {
    path: 'connect/:programId',
    handle: {
      title: 'Coffee chat',
      Skeleton: ConnectDetailPageSkeleton,
    } satisfies LoadingRouteHandle,
    lazy: async () => ({
      Component: (await import('@/modules/connect/pages')).ConnectDetailPage,
    }),
  },
  {
    path: 'settings',
    handle: {
      title: 'Settings',
      Skeleton: SettingsPageSkeleton,
    } satisfies LoadingRouteHandle,
    lazy: async () => ({
      Component: (await import('@/modules/settings/pages')).SettingsPage,
    }),
  },
  {
    path: 'insights',
    handle: {
      title: 'Insights',
      Skeleton: InsightsPageSkeleton,
    } satisfies LoadingRouteHandle,
    lazy: async () => ({
      Component: (await import('@/modules/insights/pages/insights-page'))
        .default,
    }),
  },
  {
    path: 'reports',
    handle: {
      title: 'Reports',
      Skeleton: ReportsPageSkeleton,
    } satisfies LoadingRouteHandle,
    lazy: async () => ({
      Component: (await import('@/modules/reports/pages/reports-page')).default,
    }),
  },
  {
    path: 'analytics',
    handle: {
      title: 'Analytics',
      Skeleton: AnalyticsPageSkeleton,
    } satisfies LoadingRouteHandle,
    lazy: async () => ({
      Component: (await import('@/modules/analytics/pages/analytics-page'))
        .default,
    }),
  },
  {
    path: 'members',
    handle: {
      title: 'Members',
      Skeleton: MembersPageSkeleton,
    } satisfies LoadingRouteHandle,
    lazy: async () => ({
      Component: (await import('@/modules/members/pages/members-page')).default,
    }),
  },
  {
    path: 'kudos',
    handle: {
      title: 'Kudos',
      Skeleton: KudosPageSkeleton,
    } satisfies LoadingRouteHandle,
    lazy: async () => ({
      Component: (await import('@/modules/kudos/pages/kudos-page')).default,
    }),
  },
  {
    path: 'automation',
    handle: {
      title: 'Automation',
      Skeleton: AutomationPageSkeleton,
    } satisfies LoadingRouteHandle,
    lazy: async () => ({
      Component: (await import('@/modules/automation/pages/automation-page'))
        .default,
    }),
  },
  {
    path: 'webhooks',
    handle: {
      title: 'Webhooks',
      Skeleton: WebhooksPageSkeleton,
    } satisfies LoadingRouteHandle,
    lazy: async () => ({
      Component: (await import('@/modules/webhooks/pages/webhooks-page'))
        .default,
    }),
  },
  {
    path: 'mcp',
    handle: {
      title: 'MCP',
      Skeleton: McpPageSkeleton,
    } satisfies LoadingRouteHandle,
    lazy: async () => ({
      Component: (await import('@/modules/mcp/pages/mcp-page')).default,
    }),
  },
];
