import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TestRouter } from '@/test/router';
import { chooseOption } from '@/test/select';

import MembersPage from '../pages/members-page';

const mock = vi.hoisted(() => ({
  admin: true,
  members: vi.fn(),
  invite: vi.fn(),
  role: vi.fn(),
  grant: vi.fn(),
}));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({
    data: {
      team_id: 'T1',
      user_id: 'U1',
      role: mock.admin ? 'admin' : 'member',
    },
  }),
}));

vi.mock('@/common/api/services-context', async (importOriginal) => {
  const actual = await importOriginal<object>();
  const api = {
    members: {
      listMembers: mock.members,
      inviteMember: mock.invite,
      updateMemberRole: mock.role,
      grantModuleAdmin: mock.grant,
      revokeModuleAdmin: vi.fn(),
    },
    workspace: {
      listChannels: vi
        .fn()
        .mockResolvedValue({ data: [{ id: 'C1', name: 'design' }] }),
      listModules: vi.fn().mockResolvedValue({
        data: [
          { name: 'standup', available: true, active: true, delegable: true },
        ],
      }),
    },
    standups: {
      listStandups: vi
        .fn()
        .mockResolvedValue({ data: [{ id: 1, participants: [] }] }),
    },
  };

  return {
    ...actual,
    useApi: () => api,
    useServices: () => ({ api, invalidateRouter: vi.fn() }),
  };
});

const mina = {
  id: 'U1',
  name: 'Mina',
  display_name: 'mina',
  email: 'mina@example.com',
  role: 'admin',
  module_admin: [],
  tracked: true,
  avatar: '',
  tz: 'UTC',
};

const sam = {
  ...mina,
  id: 'U2',
  name: 'Sam',
  email: 'sam@example.com',
  display_name: 'sam',
  role: 'member',
  avatar: 'https://example.com/sam.png',
};

function view(path = '/dashboard/members') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={client}>
      <TestRouter
        routeId="/dashboard/_authenticated/members"
        initialEntries={[path]}
      >
        <MembersPage />
      </TestRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mock.admin = true;
  mock.members.mockImplementation((query) =>
    Promise.resolve({ data: query.channel_id ? [mina] : [mina, sam] }),
  );
  mock.invite.mockResolvedValue({ data: { ok: true } });
});

describe('member management', () => {
  it('counts schedules that include the whole channel', async () => {
    view('/dashboard/members?channel=C1');

    expect(
      await screen.findByRole('heading', { name: 'Mina', level: 2 }),
    ).toBeInTheDocument();
    expect(screen.getByText('1 standup')).toBeInTheDocument();
  });

  it('searches the workspace for invitations even when a channel filter is active and requires a chosen member', async () => {
    const user = userEvent.setup({ delay: null });

    view('/dashboard/members?channel=C1');
    await screen.findByText('Mina');

    await user.click(screen.getByRole('button', { name: 'Invite admin' }));

    expect(
      screen.getByRole('button', { name: 'Grant admin access' }),
    ).toBeDisabled();

    const samChoice = await screen.findByRole('button', { name: /Sam/ });
    expect(samChoice.querySelector('img')).toHaveAttribute('src', sam.avatar);

    await user.click(samChoice);

    expect(mock.invite).not.toHaveBeenCalled();

    await user.click(
      screen.getByRole('button', { name: 'Grant admin access' }),
    );

    await waitFor(() =>
      expect(mock.invite).toHaveBeenCalledWith({
        user_id: 'U2',
        role: 'admin',
      }),
    );
  });

  it('does not expose workspace privileges to regular members', async () => {
    mock.admin = false;

    view();
    await screen.findByText('Sam');
    expect(
      screen.queryByRole('button', { name: 'Invite admin' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Make admin' }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Standups' })).toBeDisabled();
  });
});

it('loads selected channel labels and clears filters without losing other choices', async () => {
  mock.members.mockImplementation((query) =>
    Promise.resolve({
      data: query.channel_id ? [mina] : [mina, { ...sam, tracked: false }],
    }),
  );
  const user = userEvent.setup({ delay: null });

  view('/dashboard/members?channel=C1&role=admin');

  await waitFor(() =>
    expect(
      screen.getByRole('combobox', { name: 'Filter by channel' }),
    ).toHaveTextContent('#design'),
  );
  expect(
    screen.getByRole('combobox', { name: 'Filter by role' }),
  ).toHaveTextContent('Admins');

  await chooseOption(user, 'Filter by channel', 'All channels');

  await waitFor(() =>
    expect(mock.members).toHaveBeenCalledWith({}, expect.anything()),
  );
  expect(
    screen.getByRole('combobox', { name: 'Filter by role' }),
  ).toHaveTextContent('Admins');
  expect(screen.queryByText('Sam')).not.toBeInTheDocument();

  await chooseOption(user, 'Filter by role', 'Members');

  expect(await screen.findByText('Sam')).toBeInTheDocument();
  expect(screen.queryByText('Mina')).not.toBeInTheDocument();

  await chooseOption(user, 'Filter by role', 'All roles');
  await chooseOption(user, 'Filter by tracking', 'Not in Morgenruf');

  expect(screen.queryByText('Mina')).not.toBeInTheDocument();
  expect(screen.getByText('Sam')).toBeInTheDocument();

  await chooseOption(user, 'Filter by tracking', 'Everyone in Slack');

  expect(screen.getByText('Mina')).toBeInTheDocument();

  await chooseOption(user, 'Sort members', 'Sort by role');

  expect(
    screen.getByRole('combobox', { name: 'Sort members' }),
  ).toHaveTextContent('Sort by role');
});
