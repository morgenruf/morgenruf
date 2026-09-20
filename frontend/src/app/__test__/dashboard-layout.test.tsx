import { useState, type ComponentType } from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  createMemoryRouter,
  RouterProvider,
  type RouteObject,
} from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { deferred } from '@/test/deferred';
import { mockViewport } from '@/test/match-media';

import { DashboardHydrateFallback, DashboardLayout } from '../dashboard-layout';
import { dashboardRoutes } from '../dashboard-routes';

const state = vi.hoisted(() => ({
  sessionPending: false,
  modulesPending: false,
  canAdminister: true,
  modules: [
    { name: 'standup', available: true, active: true, missing_scopes: [] },
  ],
}));
vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({
    isPending: state.sessionPending,
    data: state.sessionPending
      ? undefined
      : { team_id: 'T1', user_id: 'U1', team_name: 'Test workspace' },
    error: null,
  }),
  usePermissions: () => ({
    isAdmin: state.canAdminister,
    canAdminister: () => state.canAdminister,
  }),
}));
vi.mock('@/common/api/use-workspace-modules', () => ({
  useWorkspaceModules: () => ({
    isPending: state.modulesPending,
    error: null,
    data: state.modules,
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

let resizeViewport: ReturnType<typeof mockViewport>;

beforeEach(() => {
  resizeViewport = mockViewport();
  state.sessionPending = false;
  state.modulesPending = false;
  state.canAdminister = true;
  state.modules = [
    { name: 'standup', available: true, active: true, missing_scopes: [] },
  ];
});

afterEach(() => vi.unstubAllGlobals());

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
  const main = screen.getByRole('main');
  main.scrollTop = 300;
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
  expect(screen.getByRole('main')).toBe(main);
  expect(main.scrollTop).toBe(0);
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

it('preserves form state and focus during search-only navigation', async () => {
  const loader = deferred<null>();
  let delay = false;
  const { router } = view('/dashboard/members', {
    members: { loader: () => (delay ? loader.promise : null) },
  });
  const input = await screen.findByRole('textbox');
  const main = screen.getByRole('main');
  main.scrollTop = 300;
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
  expect(screen.getByRole('main')).toBe(main);
  expect(main.scrollTop).toBe(300);
});

it('toggles the sidebar with its button and both keyboard shortcuts', async () => {
  view('/dashboard/members');
  const collapse = screen.getByRole('button', { name: 'Collapse sidebar' });
  expect(collapse).toHaveAttribute('aria-expanded', 'true');
  await userEvent.click(collapse);
  const expand = screen.getByRole('button', { name: 'Expand sidebar' });
  expect(expand).toHaveAttribute('aria-expanded', 'false');
  fireEvent.keyDown(window, { key: 'b', ctrlKey: true });
  expect(
    screen.getByRole('button', { name: 'Collapse sidebar' }),
  ).toBeInTheDocument();
  fireEvent.keyDown(window, { key: 'b', metaKey: true });
  expect(
    screen.getByRole('button', { name: 'Expand sidebar' }),
  ).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Members' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
});

it('filters unavailable modules and marks the current navigation link', () => {
  state.modules.push({
    name: 'kudos',
    available: false,
    active: false,
    missing_scopes: [],
  });
  view('/dashboard/members');
  const navigation = within(
    screen.getByRole('navigation', { name: 'Main navigation' }),
  );
  expect(
    navigation.queryByRole('link', { name: 'Kudos' }),
  ).not.toBeInTheDocument();
  expect(
    navigation.queryByRole('link', { name: 'Coffee chats' }),
  ).not.toBeInTheDocument();
  expect(
    navigation.getByRole('link', { name: 'Standups' }),
  ).toBeInTheDocument();
  const members = navigation.getByRole('link', { name: 'Members' });
  expect(members).toHaveAttribute('aria-current', 'page');
  expect(members).toHaveAttribute('data-active');
  expect(navigation.getByRole('link', { name: 'Reports' })).not.toHaveAttribute(
    'data-active',
  );
});

it.each([true, false])(
  'keeps exact submenu matching with admin permission %s',
  (canAdminister) => {
    state.canAdminister = canAdminister;
    state.modules.push({
      name: 'connect',
      available: true,
      active: true,
      missing_scopes: [],
    });
    view('/dashboard/connect/attendance');
    const navigation = within(
      screen.getByRole('navigation', { name: 'Main navigation' }),
    );
    expect(
      navigation.getByRole('link', { name: 'Coffee chats' }),
    ).toHaveAttribute('data-active');
    expect(
      navigation.getByRole('link', { name: 'Attendance' }),
    ).toHaveAttribute('aria-current', 'page');
    expect(
      navigation.getByRole('link', { name: 'Attendance' }),
    ).toHaveAttribute('data-active');
    expect(
      navigation.getByRole('link', { name: 'All coffee chats' }),
    ).not.toHaveAttribute('aria-current');
    expect(
      navigation.getByRole('link', { name: 'All coffee chats' }),
    ).not.toHaveAttribute('data-active');
    expect(!!navigation.queryByRole('link', { name: 'New coffee chat' })).toBe(
      canAdminister,
    );
  },
);

it('opens mobile navigation after a viewport change and closes it after selecting a route', async () => {
  view('/dashboard/standups');
  act(() => resizeViewport(390));
  await userEvent.click(
    screen.getByRole('button', { name: 'Open navigation' }),
  );
  const dialog = within(await screen.findByRole('dialog'));
  expect(
    dialog.getByRole('button', { name: 'Close navigation' }),
  ).toBeInTheDocument();
  expect(dialog.getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
  await userEvent.click(dialog.getByRole('link', { name: 'Members' }));
  await waitFor(() =>
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
  );
  expect(
    screen.getByRole('navigation', { name: 'Breadcrumb' }),
  ).toHaveTextContent('Members');
  act(() => resizeViewport(1024));
  expect(
    screen.getByRole('button', { name: 'Collapse sidebar' }),
  ).toBeInTheDocument();
});
