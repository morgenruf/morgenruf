import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

import type { Today } from '@/common/api/generated/data-contracts';
import { TestRouter } from '@/test/router';

import TodayPage from '../pages/today-page';

const mock = vi.hoisted(() => ({ today: vi.fn(), members: vi.fn() }));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({ data: { team_id: 'T1' } }),
}));

vi.mock('@/common/api/services-context', async (importOriginal) => {
  const actual = await importOriginal<object>();
  const api = {
    insights: { getToday: mock.today },
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
  mock.members.mockResolvedValue({ data: [] });
});

function renderToday(overrides: Partial<Today> = {}) {
  const today: Today = {
    date: '2026-09-20',
    counts: { answered: 0, expected: 0, awaiting: 0, blocked: 0 },
    responses: [],
    awaiting: [],
    blocked: [],
    kudos: [],
    next_chat: null,
    ...overrides,
  };
  mock.today.mockResolvedValue({ data: today });

  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <TestRouter routeId="/dashboard/_authenticated/today">
        <TodayPage />
      </TestRouter>
    </QueryClientProvider>,
  );
}

it('distinguishes an unscheduled day from a completed scheduled day', async () => {
  renderToday();

  await screen.findByText('Today’s responses');
  expect(screen.getAllByText('Nobody is scheduled today')).toHaveLength(2);
  expect(screen.queryByText('Everyone has replied')).not.toBeInTheDocument();
  expect(screen.queryByText('This morning')).not.toBeInTheDocument();
});

it('keeps the completed-day message when everyone scheduled has replied', async () => {
  renderToday({
    counts: { answered: 2, expected: 2, awaiting: 0, blocked: 0 },
  });

  expect(await screen.findByText('Everyone has replied')).toBeInTheDocument();
  expect(
    screen.queryByText('Nobody is scheduled today'),
  ).not.toBeInTheDocument();
});

it('uses directory identities across responses, blockers, awaiting badges, and recognition', async () => {
  mock.members.mockResolvedValue({
    data: [
      { id: 'U1', name: 'Priya Sharma', avatar: '/priya.jpg' },
      { id: 'U2', name: 'Marcus Chen', avatar: '/marcus.jpg' },
    ],
  });

  const { container } = renderToday({
    counts: { answered: 1, expected: 2, awaiting: 1, blocked: 1 },
    responses: [
      {
        user_id: 'U1',
        real_name: 'Previous Priya',
        today: 'Prepare the release.',
        yesterday: null,
        blockers: 'Waiting for access.',
        has_blockers: true,
        mood: null,
        schedule_id: 1,
        standup_date: '2026-09-20',
        submitted_at: null,
      },
    ],
    blocked: [
      {
        user_id: 'U1',
        real_name: 'Previous Priya',
        blockers: 'Waiting for access.',
        submitted_at: null,
      },
    ],
    awaiting: [{ user_id: 'U2', real_name: 'Previous Marcus' }],
    kudos: [
      {
        id: 1,
        from_user: 'U1',
        from_name: 'Previous Priya',
        to_user: 'U2',
        to_name: 'Previous Marcus',
        message: 'Thanks for the review.',
        created_at: '2026-09-20T09:00:00Z',
      },
    ],
  });

  await waitFor(() =>
    expect(screen.getAllByText('Priya Sharma')).toHaveLength(3),
  );
  expect(screen.getAllByText('Marcus Chen')).toHaveLength(2);
  expect(container.querySelectorAll('img[src="/priya.jpg"]')).toHaveLength(3);
  expect(container.querySelectorAll('img[src="/marcus.jpg"]')).toHaveLength(2);
  expect(screen.queryByText('Previous Priya')).not.toBeInTheDocument();
  expect(mock.members).toHaveBeenCalledTimes(1);
});
