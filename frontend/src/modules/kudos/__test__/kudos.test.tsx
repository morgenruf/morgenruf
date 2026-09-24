import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

import type { Member } from '@/common/api/generated/data-contracts';
import { deferred } from '@/test/deferred';
import { TestRouter } from '@/test/router';
import { chooseOption } from '@/test/select';

import KudosPage from '../pages/kudos-page';

const mock = vi.hoisted(() => ({
  config: vi.fn(),
  save: vi.fn(),
  leaderboard: vi.fn(),
  givers: vi.fn(),
  feed: vi.fn(),
  members: vi.fn(),
}));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({
    data: { team_id: 'T1', role: 'member', module_admin: ['kudos'] },
  }),
}));

vi.mock('@/common/api/services-context', async (importOriginal) => {
  const actual = await importOriginal<object>();
  const api = {
    kudos: {
      getConfig: mock.config,
      updateConfig: mock.save,
      listKudos: mock.feed,
      getLeaderboard: mock.leaderboard,
      getGivers: mock.givers,
    },
    members: { listMembers: mock.members },
  };

  return {
    ...actual,
    useApi: () => api,
    useServices: () => ({ api, invalidateRouter: vi.fn() }),
  };
});

beforeEach(() => {
  vi.clearAllMocks();

  mock.leaderboard.mockResolvedValue({ data: [] });
  mock.givers.mockResolvedValue({ data: [] });
  mock.feed.mockResolvedValue({ data: [] });
  mock.members.mockResolvedValue({ data: [] });

  mock.config.mockResolvedValue({
    data: { emoji: ':morgenruf:', daily_allowance: 5, token_auto: true },
  });

  mock.save.mockImplementation((data) => Promise.resolve({ data }));
});

it('previews the chosen token and disabled allowance, preserving unsaved edits during refetch', async () => {
  const user = userEvent.setup({ delay: null });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={client}>
      <TestRouter routeId="/dashboard/_authenticated/kudos">
        <KudosPage />
      </TestRouter>
    </QueryClientProvider>,
  );

  const emoji = await screen.findByLabelText('Emoji or Slack token');
  await user.clear(emoji);
  await user.type(emoji, ':custom:');

  const allowance = screen.getByLabelText('Daily allowance');
  await user.clear(allowance);
  await user.type(allowance, '0');

  expect(screen.getByText('Giving is switched off')).toBeInTheDocument();

  await client.invalidateQueries({
    queryKey: ['workspace', 'T1', 'kudos', 'config'],
  });

  expect(emoji).toHaveValue(':custom:');

  await user.click(screen.getByRole('button', { name: 'Save settings' }));

  await waitFor(() =>
    expect(mock.save).toHaveBeenCalledWith({
      emoji: ':custom:',
      daily_allowance: 0,
    }),
  );
});

it('shows the selected period on load and requests numeric days after changing it', async () => {
  const user = userEvent.setup({ delay: null });

  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <TestRouter
        routeId="/dashboard/_authenticated/kudos"
        initialEntries={['/dashboard/kudos?days=30']}
      >
        <KudosPage />
      </TestRouter>
    </QueryClientProvider>,
  );

  const period = await screen.findByRole('combobox', {
    name: 'Leaderboard period',
  });
  expect(period).toHaveTextContent('Last 30 days');

  await chooseOption(user, 'Leaderboard period', 'Last 90 days');

  expect(period).toHaveTextContent('Last 90 days');
  await waitFor(() =>
    expect(mock.leaderboard).toHaveBeenCalledWith(
      { days: 90 },
      expect.anything(),
    ),
  );
  expect(mock.givers).toHaveBeenCalledWith({ days: 90 }, expect.anything());
  expect(mock.members).toHaveBeenCalledTimes(1);
});

const members: Member[] = [
  {
    id: 'U1',
    name: 'Priya Sharma',
    display_name: 'priya',
    avatar: '/priya.jpg',
    email: null,
    module_admin: [],
    role: 'member',
    tracked: true,
    tz: null,
  },
  {
    id: 'U2',
    name: null,
    display_name: 'Marcus Chen',
    avatar: '/marcus.jpg',
    email: null,
    module_admin: [],
    role: 'member',
    tracked: true,
    tz: null,
  },
];

function populatedKudos() {
  mock.leaderboard.mockResolvedValue({
    data: [{ to_user: 'U2', received: 3, last_kudos: null }],
  });
  mock.givers.mockResolvedValue({
    data: [{ user_id: 'U1', given: 3, last_given: null }],
  });
  mock.feed.mockResolvedValue({
    data: [
      {
        id: 1,
        from_user: 'U1',
        from_name: 'Previous Priya',
        to_user: 'U2',
        to_name: 'Previous Marcus',
        message: 'Thanks for helping with the release.',
        created_at: '2026-09-20T09:00:00Z',
      },
    ],
  });
}

function renderKudos() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <TestRouter routeId="/dashboard/_authenticated/kudos">
        <KudosPage />
      </TestRouter>
    </QueryClientProvider>,
  );
}

it('uses directory names and avatars for both leaderboard and recognition participants', async () => {
  populatedKudos();
  mock.members.mockResolvedValue({ data: members });

  const { container } = renderKudos();

  await waitFor(() =>
    expect(screen.getAllByText('Priya Sharma')).toHaveLength(2),
  );
  expect(screen.getAllByText('Marcus Chen')).toHaveLength(2);
  expect(container.querySelectorAll('img[src="/priya.jpg"]')).toHaveLength(2);
  expect(container.querySelectorAll('img[src="/marcus.jpg"]')).toHaveLength(2);
  expect(screen.queryByText('Previous Priya')).not.toBeInTheDocument();
  expect(mock.members).toHaveBeenCalledTimes(1);
});

it('shows available names while the directory loads, then updates all identities', async () => {
  populatedKudos();
  const directory = deferred<{ data: Member[] }>();
  mock.members.mockReturnValue(directory.promise);

  renderKudos();

  expect(await screen.findByText('Previous Priya')).toBeInTheDocument();
  expect(screen.getByText('Previous Marcus')).toBeInTheDocument();
  expect(screen.getByText('U1')).toBeInTheDocument();
  expect(screen.getByText('U2')).toBeInTheDocument();
  expect(
    screen.getByText('Thanks for helping with the release.'),
  ).toBeInTheDocument();

  await act(async () => directory.resolve({ data: members }));

  await waitFor(() =>
    expect(screen.getAllByText('Priya Sharma')).toHaveLength(2),
  );
  expect(screen.getAllByText('Marcus Chen')).toHaveLength(2);
  expect(screen.queryByText('Previous Priya')).not.toBeInTheDocument();
});

it('keeps recognition and leaderboards usable if the directory fails', async () => {
  populatedKudos();
  mock.members.mockRejectedValue(new Error('Directory unavailable'));

  const { container } = renderKudos();

  expect(await screen.findByText('Previous Priya')).toBeInTheDocument();
  expect(screen.getByText('Previous Marcus')).toBeInTheDocument();
  expect(screen.getByText('U1')).toBeInTheDocument();
  expect(screen.getByText('U2')).toBeInTheDocument();
  expect(screen.getByText('PP')).toBeInTheDocument();
  expect(screen.getByText('PM')).toBeInTheDocument();
  expect(
    container.querySelector('img[src="/priya.jpg"]'),
  ).not.toBeInTheDocument();
  expect(screen.queryByText('Directory unavailable')).not.toBeInTheDocument();
});

it('lets independently loaded sections appear while a leaderboard is pending', async () => {
  const receivers = deferred<{ data: never[] }>();
  mock.leaderboard.mockReturnValue(receivers.promise);

  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <TestRouter routeId="/dashboard/_authenticated/kudos">
        <KudosPage />
      </TestRouter>
    </QueryClientProvider>,
  );

  await screen.findByLabelText('Emoji or Slack token');
  expect(
    screen.getByRole('status', { name: 'Loading leaderboard…' }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole('status', { name: 'Loading recognition…' }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('status', { name: 'Loading kudos settings…' }),
  ).not.toBeInTheDocument();

  await act(async () => receivers.resolve({ data: [] }));

  await waitFor(() =>
    expect(screen.queryByRole('status')).not.toBeInTheDocument(),
  );
});
