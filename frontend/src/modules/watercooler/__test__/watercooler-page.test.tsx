import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

import type { WatercoolerOverview } from '@/common/api/generated/data-contracts';
import { TestRouter } from '@/test/router';

import WatercoolerPage from '../pages/watercooler-page';

const mock = vi.hoisted(() => ({
  overview: vi.fn(),
  save: vi.fn(),
  remove: vi.fn(),
  post: vi.fn(),
  add: vi.fn(),
  update: vi.fn(),
  hide: vi.fn(),
}));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({
    data: { team_id: 'T1', role: 'admin', module_admin: [] },
  }),
}));

vi.mock('@/common/api/services-context', async (importOriginal) => {
  const actual = await importOriginal<object>();
  const api = {
    watercooler: {
      getWatercooler: mock.overview,
      saveWatercoolerChannel: mock.save,
      deleteWatercoolerChannel: mock.remove,
      postWatercoolerNow: mock.post,
      addWatercoolerQuestion: mock.add,
      updateWatercoolerQuestion: mock.update,
      setWatercoolerHidden: mock.hide,
    },
    workspace: {
      listChannels: vi.fn().mockResolvedValue({
        data: [
          { id: 'C1', name: 'general' },
          { id: 'C2', name: 'random' },
        ],
      }),
    },
  };

  return {
    ...actual,
    useApi: () => api,
    useServices: () => ({ api, invalidateRouter: vi.fn() }),
  };
});

const overview = (can_manage = true): WatercoolerOverview => ({
  channels: [
    {
      channel_id: 'C1',
      days: ['mon', 'wed', 'fri'],
      post_time: '10:00',
      timezone: 'UTC',
      source: 'both',
      categories: ['light', 'work', 'remote', 'this_or_that'],
      active: false,
      paused_reason: 'not_in_channel',
    },
  ],
  questions: [
    { id: 4, text: 'What did you build this week?', archived: false },
  ],
  bank: [
    { key: 'light-001', category: 'light', text: 'Best snack?', hidden: false },
    { key: 'work-001', category: 'work', text: 'Best tool?', hidden: true },
  ],
  categories: [
    { key: 'light', label: 'Light' },
    { key: 'work', label: 'Work' },
    { key: 'remote', label: 'Remote life' },
    { key: 'this_or_that', label: 'This or that' },
  ],
  can_manage,
  max_channels: 20,
  max_questions: 500,
});

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={client}>
      <TestRouter routeId="/dashboard/_authenticated/watercooler">
        <WatercoolerPage />
      </TestRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mock.overview.mockResolvedValue({ data: overview() });
  mock.save.mockResolvedValue({ data: overview().channels[0] });
  mock.post.mockResolvedValue({ data: { posted: true } });
  mock.add.mockResolvedValue({ data: { id: 5, text: 'x', archived: false } });
  mock.update.mockResolvedValue({ data: {} });
  mock.hide.mockResolvedValue({ data: {} });
  mock.remove.mockResolvedValue({ data: { ok: true } });
});

it('shows why a channel is paused and posts one now', async () => {
  const user = userEvent.setup({ delay: null });
  renderPage();

  const list = await screen.findByRole('list', {
    name: 'Watercooler channels',
  });
  expect(
    within(list).getByText('Paused: Morgenruf is not in this channel'),
  ).toBeInTheDocument();
  await user.click(within(list).getByRole('button', { name: 'Post one now' }));
  await waitFor(() =>
    expect(mock.post).toHaveBeenCalledWith({ channelId: 'C1' }),
  );
});

it('adds a channel with the chosen days and only offers channels not set up yet', async () => {
  const user = userEvent.setup({ delay: null });
  renderPage();

  const form = await screen.findByRole('form', { name: 'Add a channel' });
  const select = within(form).getByRole('combobox', { name: 'Channel' });
  expect(within(select).queryByRole('option', { name: '#general' })).toBeNull();
  await user.selectOptions(select, 'C2');
  await user.click(within(form).getByRole('checkbox', { name: 'Fri' }));
  await user.click(within(form).getByRole('checkbox', { name: 'Tue' }));
  await user.click(within(form).getByRole('button', { name: 'Add channel' }));

  await waitFor(() =>
    expect(mock.save).toHaveBeenCalledWith(
      { channelId: 'C2' },
      expect.objectContaining({
        days: ['mon', 'wed', 'tue'],
        post_time: '10:00',
        source: 'both',
        active: true,
      }),
    ),
  );
});

it('hides a built-in question and adds one of our own', async () => {
  const user = userEvent.setup({ delay: null });
  renderPage();

  await user.click(
    await screen.findByRole('button', { name: 'Hide: Best snack?' }),
  );
  await waitFor(() =>
    expect(mock.hide).toHaveBeenCalledWith(
      { key: 'light-001' },
      { hidden: true },
    ),
  );

  await user.type(
    screen.getByRole('textbox', { name: 'New question' }),
    'Favourite keyboard shortcut?',
  );
  await user.click(screen.getByRole('button', { name: 'Add' }));
  await waitFor(() =>
    expect(mock.add).toHaveBeenCalledWith({
      text: 'Favourite keyboard shortcut?',
    }),
  );
});

it('is read only for people who do not run it', async () => {
  mock.overview.mockResolvedValue({ data: overview(false) });
  renderPage();

  expect(
    await screen.findByText('What did you build this week?'),
  ).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Post one now' })).toBeNull();
  expect(screen.queryByRole('form', { name: 'Add a channel' })).toBeNull();
  expect(screen.queryByRole('button', { name: /^Hide:/ })).toBeNull();
  expect(screen.getByText('Hidden')).toBeInTheDocument();
});
