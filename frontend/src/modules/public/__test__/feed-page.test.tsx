import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { expect, it, vi } from 'vitest';

import FeedPage from '../pages/feed-page';

const members = vi.hoisted(() => vi.fn());

vi.mock('@/common/api/client', () => ({
  api: {
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
  },
}));

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
      <MemoryRouter initialEntries={['/feed/public-token']}>
        <Routes>
          <Route path="/feed/:token" element={<FeedPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText('Mina Park')).toBeInTheDocument();
  expect(screen.getByText('MP')).toHaveAttribute('aria-hidden', 'true');
  expect(screen.getByText('Shipped')).toBeInTheDocument();
  expect(members).not.toHaveBeenCalled();
});
