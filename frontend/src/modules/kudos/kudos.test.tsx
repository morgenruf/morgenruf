import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { beforeEach, expect, it, vi } from 'vitest';

import { deferred } from '@/test/deferred';
import { chooseOption } from '@/test/select';

import KudosPage from './pages/kudos-page';

const mock = vi.hoisted(() => ({
  config: vi.fn(),
  save: vi.fn(),
  leaderboard: vi.fn(),
  givers: vi.fn(),
}));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({
    data: { team_id: 'T1', role: 'member', module_admin: ['kudos'] },
  }),
}));

vi.mock('@/common/api/client', () => ({
  api: {
    kudos: {
      getConfig: mock.config,
      updateConfig: mock.save,
      listKudos: vi.fn().mockResolvedValue({ data: [] }),
      getLeaderboard: mock.leaderboard,
      getGivers: mock.givers,
    },
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  mock.leaderboard.mockResolvedValue({ data: [] });
  mock.givers.mockResolvedValue({ data: [] });

  mock.config.mockResolvedValue({
    data: { emoji: ':morgenruf:', daily_allowance: 5, token_auto: true },
  });

  mock.save.mockImplementation((data) => Promise.resolve({ data }));
});

it('previews the chosen token and disabled allowance, preserving unsaved edits during refetch', async () => {
  const user = userEvent.setup();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <KudosPage />
      </MemoryRouter>
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
  const user = userEvent.setup();
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={['/dashboard/kudos?days=30']}>
        <KudosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const period = screen.getByRole('combobox', { name: 'Leaderboard period' });
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
      <MemoryRouter>
        <KudosPage />
      </MemoryRouter>
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
