import { RouterProvider } from '@tanstack/react-router';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

import { createTestRouter } from '@/test/router';

import ReportsPage from '../reports-page';

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({ data: { team_id: 'T1' } }),
}));

vi.mock('@/common/api/services-context', () => ({ useApi: () => ({}) }));

vi.mock('../../hooks', () => ({
  useReports: () => ({
    reports: {
      isPending: false,
      data: { total_days: 0, participation: [], standups: [] },
    },
    members: {
      isPending: false,
      data: [{ id: 'U1', name: 'Ada' }],
      person: () => ({ name: 'Ada' }),
    },
  }),
  exportReports: vi.fn(),
}));

it('preserves both dates and the member when date filters change before the next render', async () => {
  const router = createTestRouter({
    routeId: '/dashboard/_authenticated/reports',
    children: <ReportsPage />,
    initialEntries: ['/dashboard/reports?user_id=U1'],
  });

  await router.load();
  render(<RouterProvider router={router} />);

  const from = screen.getByLabelText('From', { exact: true });
  const to = screen.getByLabelText('To', { exact: true });

  await act(async () => {
    fireEvent.change(from, { target: { value: '2026-09-01' } });
    fireEvent.change(to, { target: { value: '2026-09-19' } });
  });

  const params = new URLSearchParams(router.state.location.searchStr);
  expect(params.get('date_from')).toBe('2026-09-01');
  expect(params.get('date_to')).toBe('2026-09-19');
  expect(params.get('user_id')).toBe('U1');
  expect(from).toHaveValue('2026-09-01');
  expect(to).toHaveValue('2026-09-19');
});
