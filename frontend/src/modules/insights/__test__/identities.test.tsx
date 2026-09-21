import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

import InsightsPage from '../pages/insights-page';

const members = vi.hoisted(() => vi.fn());

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({ data: { team_id: 'T1' } }),
}));

vi.mock('@/common/api/client', () => ({
  api: {
    members: { listMembers: members },
    insights: {
      getInsights: async () => ({
        data: {
          unrecognised: [
            {
              user_id: 'U1',
              real_name: 'Response name',
              standups: 4,
              kudos: 0,
            },
          ],
          stuck: [
            {
              user_id: 'U2',
              real_name: 'Another response name',
              days: 3,
              text: 'Waiting for access',
              first_seen: '2026-09-17',
              last_seen: '2026-09-20',
            },
          ],
        },
      }),
    },
  },
}));

beforeEach(() => vi.clearAllMocks());

function view() {
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

it('resolves both insight identities from the same directory', async () => {
  members.mockResolvedValue({
    data: [
      { id: 'U1', name: 'Mina', avatar: 'https://example.com/mina.png' },
      { id: 'U2', display_name: 'Sam', avatar: 'https://example.com/sam.png' },
    ],
  });
  const { container } = view();
  expect(await screen.findByText('Mina')).toBeInTheDocument();
  expect(await screen.findByText('Sam')).toBeInTheDocument();
  expect(container.querySelectorAll('img')).toHaveLength(2);
  expect(members).toHaveBeenCalledOnce();
});

it('keeps insight content and response names visible when the directory fails', async () => {
  members.mockRejectedValue(new Error('Directory unavailable'));
  view();
  expect(await screen.findByText('Response name')).toBeInTheDocument();
  expect(screen.getByText('Another response name')).toBeInTheDocument();
  expect(screen.getByText('Waiting for access')).toBeInTheDocument();
  expect(
    screen.queryByText('Could not load this view'),
  ).not.toBeInTheDocument();
});
