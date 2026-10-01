import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

import type { Poll } from '@/common/api/generated/data-contracts';
import { TestRouter } from '@/test/router';

import PollsPage from '../pages/polls-page';

const mock = vi.hoisted(() => ({
  list: vi.fn(),
  close: vi.fn(),
  members: vi.fn(),
}));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({
    data: { team_id: 'T1', role: 'member', module_admin: [] },
  }),
}));

vi.mock('@/common/api/services-context', async (importOriginal) => {
  const actual = await importOriginal<object>();
  const api = {
    polls: { listPolls: mock.list, closePoll: mock.close },
    members: { listMembers: mock.members },
    workspace: {
      listChannels: vi
        .fn()
        .mockResolvedValue({ data: [{ id: 'C1', name: 'general' }] }),
    },
  };

  return {
    ...actual,
    useApi: () => api,
    useServices: () => ({ api, invalidateRouter: vi.fn() }),
  };
});

const named: Poll = {
  id: 1,
  question: 'Where should the offsite be?',
  channel_id: 'C1',
  created_by: 'U1',
  anonymous: false,
  multiple: false,
  hide_results: false,
  created_at: '2026-10-01T10:00:00Z',
  closes_at: null,
  closed_at: null,
  total_votes: 3,
  can_close: true,
  options: [
    { text: 'Lisbon', votes: 2, voters: ['U1', 'U2'] },
    { text: 'Berlin', votes: 1, voters: ['U3'] },
  ],
};

const hidden: Poll = {
  ...named,
  id: 2,
  question: 'How was the sprint?',
  anonymous: true,
  hide_results: true,
  total_votes: 4,
  can_close: false,
  options: [
    { text: 'Good', votes: null, voters: null },
    { text: 'Rough', votes: null, voters: null },
  ],
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={client}>
      <TestRouter routeId="/dashboard/_authenticated/polls">
        <PollsPage />
      </TestRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mock.members.mockResolvedValue({
    data: [
      { id: 'U1', name: 'Alex Morgan' },
      { id: 'U2', name: 'Jamie Chen' },
    ],
  });
  mock.list.mockResolvedValue({ data: [named, hidden] });
  mock.close.mockResolvedValue({ data: { ...named, closed_at: 'now' } });
});

it('lists polls and shows results with voter names when expanded', async () => {
  const user = userEvent.setup({ delay: null });
  renderPage();

  const question = await screen.findByRole('button', {
    name: 'Where should the offsite be?',
  });
  expect(screen.getByText('How was the sprint?')).toBeInTheDocument();
  expect(await screen.findAllByText('#general')).toHaveLength(2);

  await user.click(question);
  expect(question).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByText('2 (67%)')).toBeInTheDocument();
  expect(
    await screen.findByText('Alex Morgan, Jamie Chen'),
  ).toBeInTheDocument();
});

it('hides counts while a poll keeps its results hidden', async () => {
  const user = userEvent.setup({ delay: null });
  renderPage();

  await user.click(
    await screen.findByRole('button', { name: 'How was the sprint?' }),
  );
  expect(
    screen.getByText('4 votes so far. Results show when the poll closes.'),
  ).toBeInTheDocument();
  expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  expect(screen.queryByText(/%\)/)).not.toBeInTheDocument();
});

it('offers Close only where allowed and confirms first', async () => {
  const user = userEvent.setup({ delay: null });
  renderPage();

  const buttons = await screen.findAllByRole('button', { name: 'Close' });
  expect(buttons).toHaveLength(1);

  await user.click(buttons[0]);
  await user.click(await screen.findByRole('button', { name: 'Close poll' }));
  await waitFor(() => expect(mock.close).toHaveBeenCalledWith({ pollId: 1 }));
});

it('explains how to start when there are no polls', async () => {
  mock.list.mockResolvedValue({ data: [] });
  renderPage();

  expect(
    await screen.findByText(
      'No polls yet. Type /morgenruf poll in any channel Morgenruf is in.',
    ),
  ).toBeInTheDocument();
});
