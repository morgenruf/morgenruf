import { createBrowserRouter, redirect } from 'react-router';

import { LoginPageSkeleton } from '@/modules/auth/loading';
import { FeedPageSkeleton, ResultPageSkeleton } from '@/modules/public/loading';

import { DashboardHydrateFallback, DashboardLayout } from './dashboard-layout';
import { dashboardRoutes } from './dashboard-routes';
import { NotFound, RouteError } from './route-errors';

export const router = createBrowserRouter([
  { path: '/', loader: () => redirect('/dashboard/standups') },
  {
    path: '/dashboard/login',
    HydrateFallback: LoginPageSkeleton,
    lazy: async () => ({
      Component: (await import('@/modules/auth/pages/login-page')).default,
    }),
  },
  {
    path: '/auth/result',
    HydrateFallback: ResultPageSkeleton,
    lazy: async () => ({
      Component: (await import('@/modules/public/pages/result-page')).default,
    }),
  },
  {
    path: '/email/result',
    HydrateFallback: ResultPageSkeleton,
    lazy: async () => ({
      Component: (await import('@/modules/public/pages/result-page')).default,
    }),
  },
  {
    path: '/connect/zoom/result',
    HydrateFallback: ResultPageSkeleton,
    lazy: async () => ({
      Component: (await import('@/modules/public/pages/result-page')).default,
    }),
  },
  {
    path: '/feed/:token',
    HydrateFallback: FeedPageSkeleton,
    lazy: async () => ({
      Component: (await import('@/modules/public/pages/feed-page')).default,
    }),
  },
  {
    path: '/dashboard',
    HydrateFallback: DashboardHydrateFallback,
    Component: DashboardLayout,
    ErrorBoundary: RouteError,
    children: dashboardRoutes,
  },
  {
    path: '*',
    Component: NotFound,
  },
]);
