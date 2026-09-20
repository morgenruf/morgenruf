import { useState, type ComponentType } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  createMemoryRouter,
  RouterProvider,
  type RouteObject,
} from 'react-router';
import { beforeEach, expect, it, vi } from 'vitest';

import { deferred } from '@/test/deferred';

import { DashboardHydrateFallback, DashboardLayout } from './dashboard-layout';
import { dashboardRoutes } from './dashboard-routes';

const state = vi.hoisted(() => ({
  sessionPending: false,
  modulesPending: false,
}));
vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({
    isPending: state.sessionPending,
    data: state.sessionPending
      ? undefined
      : { team_id: 'T1', user_id: 'U1', team_name: 'Test workspace' },
    error: null,
  }),
  usePermissions: () => ({ isAdmin: true, canAdminister: () => true }),
}));
vi.mock('@/common/api/use-workspace-modules', () => ({
  useWorkspaceModules: () => ({
    isPending: state.modulesPending,
    error: null,
    data: [
      { name: 'standup', available: true, active: true, missing_scopes: [] },
    ],
  }),
}));

function FormPage() {
  const [value, setValue] = useState('');
  return (
    <input
      aria-label="Unsaved note"
      value={value}
      onChange={(event) => setValue(event.target.value)}
    />
  );
}

function view(
  initial: string,
  overrides: Record<string, Partial<RouteObject>> = {},
) {
  const routes = dashboardRoutes
    .filter((route) => route.path)
    .map(
      (route) =>
        ({
          ...route,
          lazy: undefined,
          Component: FormPage,
          ...overrides[route.path!],
        }) as RouteObject,
    );
  const router = createMemoryRouter(
    [
      {
        path: '/dashboard',
        Component: DashboardLayout,
        HydrateFallback: DashboardHydrateFallback,
        children: routes,
      },
    ],
    { initialEntries: [initial] },
  );
  const result = render(<RouterProvider router={router} />);
  return { router, ...result };
}

beforeEach(() => {
  state.sessionPending = false;
  state.modulesPending = false;
});

it('uses the requested page inside the shell during cold lazy loading', async () => {
  const page = deferred<{ Component: ComponentType }>();
  view('/dashboard/members', {
    members: { Component: undefined, lazy: () => page.promise },
  });
  expect(
    screen.getByRole('status', { name: 'Opening your workspace…' }),
  ).toBeInTheDocument();
  expect(screen.getByText('Members')).toBeInTheDocument();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  await act(async () => page.resolve({ Component: FormPage }));
  expect(await screen.findByRole('textbox')).toBeInTheDocument();
});

it('keeps page children unmounted while session or module availability is pending', async () => {
  state.sessionPending = true;
  const { rerender, router } = view('/dashboard/standups');
  expect(
    screen.getByRole('status', { name: 'Opening your workspace…' }),
  ).toBeInTheDocument();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  state.sessionPending = false;
  state.modulesPending = true;
  rerender(<RouterProvider key="modules" router={router} />);
  expect(
    screen.getByRole('status', { name: 'Loading standups…' }),
  ).toBeInTheDocument();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  state.modulesPending = false;
  rerender(<RouterProvider key="ready" router={router} />);
  expect(screen.getByRole('textbox')).toBeInTheDocument();
});

it('shows the latest destination skeleton and preserves the collapsed shell through rapid navigation', async () => {
  const members = deferred<{ Component: ComponentType }>();
  const reports = deferred<{ Component: ComponentType }>();
  const { router } = view('/dashboard/standups', {
    members: { Component: undefined, lazy: () => members.promise },
    reports: { Component: undefined, lazy: () => reports.promise },
  });
  await userEvent.click(
    screen.getByRole('button', { name: 'Collapse sidebar' }),
  );
  const shell = screen.getByRole('button', { name: 'Expand sidebar' });
  let first!: Promise<void>;
  act(() => {
    first = router.navigate('/dashboard/members');
  });
  expect(
    await screen.findByRole('status', { name: 'Loading members…' }),
  ).toBeInTheDocument();
  let second!: Promise<void>;
  act(() => {
    second = router.navigate('/dashboard/reports');
  });
  expect(
    await screen.findByRole('status', { name: 'Loading reports…' }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole('status', { name: 'Loading members…' }),
  ).not.toBeInTheDocument();
  await act(async () => {
    members.resolve({ Component: FormPage });
    await first;
  });
  expect(
    screen.getByRole('status', { name: 'Loading reports…' }),
  ).toBeInTheDocument();
  await act(async () => {
    reports.resolve({ Component: FormPage });
    await second;
  });
  expect(screen.getByRole('button', { name: 'Expand sidebar' })).toBe(shell);
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

it('preserves form state and focus during search-only navigation', async () => {
  const loader = deferred<null>();
  let delay = false;
  const { router } = view('/dashboard/members', {
    members: { loader: () => (delay ? loader.promise : null) },
  });
  const input = await screen.findByRole('textbox');
  await userEvent.type(input, 'Keep this draft');
  delay = true;
  let navigation!: Promise<void>;
  act(() => {
    navigation = router.navigate('/dashboard/members?q=alex');
  });
  await waitFor(() => expect(router.state.navigation.state).toBe('loading'));
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
  expect(input).toHaveValue('Keep this draft');
  expect(input).toHaveFocus();
  await act(async () => {
    loader.resolve(null);
    await navigation;
  });
  expect(screen.getByRole('textbox')).toBe(input);
});
