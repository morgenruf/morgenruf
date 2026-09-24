import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

import { TestRouter } from '@/test/router';

import FeedPage from '../pages/feed-page';

const members = vi.hoisted(() => vi.fn());

vi.mock('@/common/api/services-context', async (importOriginal) => {
  const actual = await importOriginal<object>();
  const api = {
    public: {
      getFeed: async () => ({
        data: {
          date: '2026-09-20',
          title: 'Team standup',
          standups: [
            {
              user_id: 'U1',
              user_name: 'Mina Park',
              yesterday: 'Shipped',
              today: 'Review',
              blockers: '',
            },
          ],
        },
      }),
    },
    members: { listMembers: members },
  };

  return {
    ...actual,
    useApi: () => api,
    useServices: () => ({ api, invalidateRouter: vi.fn() }),
  };
});

vi.mock('@/common/components/theme-toggle', () => ({
  ThemeToggle: () => null,
}));

it('shows public-feed initials without requesting a private directory', async () => {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <TestRouter
        routeId="/feed/$token"
        initialEntries={['/feed/public-token']}
      >
        <FeedPage />
      </TestRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByText('Mina Park')).toBeInTheDocument();
  expect(screen.getByText('MP')).toHaveAttribute('aria-hidden', 'true');
  expect(screen.getByText('Shipped')).toBeInTheDocument();
  expect(members).not.toHaveBeenCalled();
});
