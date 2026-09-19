import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router/dom';

import { NavigationLoadingBar } from './app/navigation-loading-bar';
import { AppProviders } from './app/providers';
import { router } from './app/router';

import './common/styles/globals.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProviders>
      <NavigationLoadingBar router={router} />
      <RouterProvider router={router} />
    </AppProviders>
  </StrictMode>,
);
