import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

import InsightsPage from '../pages/insights-page';

const mock = vi.hoisted(() => ({ insights: vi.fn(), members: vi.fn() }));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({ data: { team_id: 'T1' } }),
}));

vi.mock('@/common/api/services-context', async (importOriginal) => {
  const actual = await importOriginal<object>();
  const api = {
    members: { listMembers: mock.members },
    insights: { getInsights: mock.insights },
  };

  return {
    ...actual,
    useApi: () => api,
    useServices: () => ({ api, invalidateRouter: vi.fn() }),
  };
});

beforeEach(() => {
  vi.clearAllMocks();
  mock.members.mockResolvedValue({ data: [{ id: 'U1', name: 'Mina' }] });
});

function view(data: object) {
  mock.insights.mockResolvedValue({
    data: { window_days: 30, stuck: [], ...data },
  });

  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <InsightsPage />
    </QueryClientProvider>,
  );
}

it('lists contributors when nobody has received kudos', async () => {
  view({
    contributors: 1,
    unrecognised: [
      {
        user_id: 'U1',
        real_name: 'Mina',
        standups: 1,
        last_standup: '2026-09-28',
        kudos: 0,
      },
    ],
  });

  expect(await screen.findByText('Mina')).toBeInTheDocument();
  expect(screen.getByText('No kudos')).toBeInTheDocument();
  expect(
    screen.queryByText('Everyone has been recognised'),
  ).not.toBeInTheDocument();
});

it('says everyone was recognised only when every contributor was thanked', async () => {
  view({ contributors: 3, unrecognised: [] });

  expect(
    await screen.findByText('Everyone has been recognised'),
  ).toBeInTheDocument();
});

it('shows a neutral state when nobody has filed a standup', async () => {
  view({ contributors: 0, unrecognised: [] });

  expect(await screen.findByText('No standups yet')).toBeInTheDocument();
  expect(
    screen.queryByText('Everyone has been recognised'),
  ).not.toBeInTheDocument();
});
