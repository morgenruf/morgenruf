import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, it, vi } from 'vitest';

import ReportsPage from '../pages/reports-page';

const reports = vi.hoisted(() => vi.fn());
vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({ data: { team_id: 'T1' } }),
}));
vi.mock('@/common/api/client', () => ({
  api: {
    reports: { getReports: reports },
    members: { listMembers: async () => ({ data: [] }) },
  },
}));

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
