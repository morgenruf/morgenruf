import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, expect, it, vi } from 'vitest';

import { deferred } from '@/test/deferred';

import ReportsPage from '../pages/reports-page';

const { reports, members } = vi.hoisted(() => ({
  reports: vi.fn(),
  members: vi.fn(),
}));
vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({ data: { team_id: 'T1' } }),
}));
vi.mock('@/common/api/client', () => ({
  api: {
    reports: { getReports: reports },
    members: { listMembers: members },
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  members.mockResolvedValue({ data: [] });
});

it('shows response identities while the directory loads and upgrades them when available', async () => {
  const directory = deferred<{
    data: { id: string; name: string; avatar: string }[];
  }>();
  members.mockReturnValue(directory.promise);
  reports.mockResolvedValue({
    data: {
      total_days: 1,
      participation: [
        {
          user_id: 'U1',
          name: 'Response name',
          expected: 1,
          responses: 1,
          total: 1,
          stars: 5,
        },
      ],
      standups: [
        {
          user_id: 'U1',
          real_name: 'Response name',
          standup_date: '2026-09-20',
          yesterday: 'Shipped',
          today: 'Review',
          blockers: '',
        },
      ],
    },
  });
  const { container } = render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={['/dashboard/reports']}>
        <ReportsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findAllByText('Response name')).toHaveLength(2);
  expect(screen.getByText('Shipped')).toBeInTheDocument();
  await act(async () =>
    directory.resolve({
      data: [
        {
          id: 'U1',
          name: 'Directory name',
          avatar: 'https://example.com/person.png',
        },
      ],
    }),
  );
  expect(await screen.findAllByText('Directory name')).toHaveLength(2);
  expect(screen.queryByText('Response name')).not.toBeInTheDocument();
  expect(
    container.querySelectorAll('img[src="https://example.com/person.png"]'),
  ).toHaveLength(2);
});

it('shows validation rather than a skeleton for a disabled invalid-range query', async () => {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter
        initialEntries={[
          '/dashboard/reports?date_from=2026-09-20&date_to=2026-09-01',
        ]}
      >
        <ReportsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(screen.getByRole('alert')).toHaveTextContent(
    'The start date must be on or before the end date.',
  );
  await screen.findByRole('combobox', { name: 'Member' });
  expect(reports).not.toHaveBeenCalled();
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});
