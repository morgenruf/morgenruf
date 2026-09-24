import type { ReactNode } from 'react';
import {
  ClientOnly,
  createRootRouteWithContext,
  HeadContent,
  Outlet,
  Scripts,
} from '@tanstack/react-router';

import { NavigationLoadingBar } from '@/app/navigation-loading-bar';
import { Toasts } from '@/app/providers';
import { NotFound, RouteError } from '@/app/route-errors';
import type { RouterContext } from '@/app/router-context';
import { DocumentFallback } from '@/app/startup-fallback';
import stylesheet from '@/common/styles/globals.css?url';

// Choose the shell before paint without making React's initial markup URL-dependent.
const startupScript = `
  var p = location.pathname.replace(/\\/+$/, '');

  document.documentElement.dataset.startupView =
    (!p || p === '/dashboard' || (p.startsWith('/dashboard/') && p !== '/dashboard/login'))
      ? 'dashboard'
      : 'public';

  try {
    var t = localStorage.getItem('morgenruf-theme') || 'system';

    if (t === 'dark' || (t === 'system' && matchMedia('(prefers-color-scheme: dark)').matches))
      document.documentElement.classList.add('dark')
  } catch (e) {}
`;

export const Route = createRootRouteWithContext<RouterContext>()({
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { name: 'theme-color', content: '#4B54E0' },
      { title: 'Morgenruf' },
    ],

    links: [
      { rel: 'icon', href: '/favicon.ico' },
      { rel: 'stylesheet', href: stylesheet },
    ],
  }),

  shellComponent: RootDocument,
  component: Outlet,
  errorComponent: RouteError,
  notFoundComponent: NotFound,
});

function RootDocument({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <HeadContent />
        <script dangerouslySetInnerHTML={{ __html: startupScript }} />
      </head>

      <body>
        <ClientOnly fallback={<DocumentFallback />}>
          <NavigationLoadingBar />
          {children}
          <Toasts />
        </ClientOnly>

        <Scripts />
      </body>
    </html>
  );
}
