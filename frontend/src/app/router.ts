import { createBrowserRouter, redirect } from 'react-router';

import { AppLayout } from '@/common/components/layout/app-layout';
import { LoadingState } from '@/common/components/page';
import { legacyDashboardPath } from '@/common/lib/routes';

import { NotFound, RouteError } from './route-errors';

export const router = createBrowserRouter([
  { path: '/', loader: () => redirect('/dashboard/standups') },
  {
    path: '/dashboard/login',
    HydrateFallback: LoadingState,
    lazy: async () => ({
      Component: (await import('@/modules/auth/pages/login-page')).default,
    }),
  },
  {
    path: '/auth/result',
    HydrateFallback: LoadingState,
    lazy: async () => ({
      Component: (await import('@/modules/public/pages/result-page')).default,
    }),
  },
  {
    path: '/email/result',
    HydrateFallback: LoadingState,
    lazy: async () => ({
      Component: (await import('@/modules/public/pages/result-page')).default,
    }),
  },
  {
    path: '/connect/zoom/result',
    HydrateFallback: LoadingState,
    lazy: async () => ({
      Component: (await import('@/modules/public/pages/result-page')).default,
    }),
  },
  {
    path: '/feed/:token',
    HydrateFallback: LoadingState,
    lazy: async () => ({
      Component: (await import('@/modules/public/pages/feed-page')).default,
    }),
  },
  {
    path: '/dashboard',
    HydrateFallback: LoadingState,
    Component: AppLayout,
    ErrorBoundary: RouteError,
    children: [
      {
        index: true,
        loader: () => redirect(legacyDashboardPath(window.location.hash)),
      },
      {
        path: 'today',
        handle: { title: 'Today' },
        lazy: async () => ({
          Component: (await import('@/modules/today/pages/today-page')).default,
        }),
      },
      {
        path: 'standups',
        handle: { title: 'Standups' },
        lazy: async () => ({
          Component: (await import('@/modules/standups/pages')).StandupsPage,
        }),
      },
      {
        path: 'connect',
        handle: { title: 'Coffee chats' },
        lazy: async () => ({
          Component: (await import('@/modules/connect/pages')).ConnectListPage,
        }),
      },
      {
        path: 'connect/new',
        handle: { title: 'New coffee chat' },
        lazy: async () => ({
          Component: (await import('@/modules/connect/pages')).ConnectNewPage,
        }),
      },
      {
        path: 'connect/attendance',
        handle: { title: 'Attendance' },
        lazy: async () => ({
          Component: (await import('@/modules/connect/pages'))
            .ConnectAttendancePage,
        }),
      },
      {
        path: 'connect/:programId',
        handle: { title: 'Coffee chat' },
        lazy: async () => ({
          Component: (await import('@/modules/connect/pages'))
            .ConnectDetailPage,
        }),
      },
      {
        path: 'settings',
        handle: { title: 'Settings' },
        lazy: async () => ({
          Component: (await import('@/modules/settings/pages')).SettingsPage,
        }),
      },
      {
        path: 'insights',
        handle: { title: 'Insights' },
        lazy: async () => ({
          Component: (await import('@/modules/insights/pages/insights-page'))
            .default,
        }),
      },
      {
        path: 'reports',
        handle: { title: 'Reports' },
        lazy: async () => ({
          Component: (await import('@/modules/reports/pages/reports-page'))
            .default,
        }),
      },
      {
        path: 'analytics',
        handle: { title: 'Analytics' },
        lazy: async () => ({
          Component: (await import('@/modules/analytics/pages/analytics-page'))
            .default,
        }),
      },
      ...(['members', 'kudos', 'automation', 'webhooks', 'mcp'] as const).map(
        (feature) => ({
          path: feature,
          handle: {
            title:
              feature === 'mcp'
                ? 'MCP'
                : feature[0].toUpperCase() + feature.slice(1),
          },
          lazy:
            feature === 'members'
              ? async () => ({
                  Component: (
                    await import('@/modules/members/pages/members-page')
                  ).default,
                })
              : feature === 'kudos'
                ? async () => ({
                    Component: (
                      await import('@/modules/kudos/pages/kudos-page')
                    ).default,
                  })
                : feature === 'automation'
                  ? async () => ({
                      Component: (
                        await import('@/modules/automation/pages/automation-page')
                      ).default,
                    })
                  : feature === 'webhooks'
                    ? async () => ({
                        Component: (
                          await import('@/modules/webhooks/pages/webhooks-page')
                        ).default,
                      })
                    : async () => ({
                        Component: (
                          await import('@/modules/mcp/pages/mcp-page')
                        ).default,
                      }),
        }),
      ),
    ],
  },
  {
    path: '*',
    Component: NotFound,
  },
]);
