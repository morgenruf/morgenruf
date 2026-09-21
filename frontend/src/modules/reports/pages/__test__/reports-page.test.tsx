import { flushSync } from 'react-dom';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { expect, it, vi } from 'vitest';

import ReportsPage from '../reports-page';

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({ data: { team_id: 'T1' } }),
}));
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

it('preserves both dates and the member when date filters change before the next render', () => {
  const router = createMemoryRouter(
    [{ path: '/dashboard/reports', element: <ReportsPage /> }],
    { initialEntries: ['/dashboard/reports?user_id=U1'] },
  );
  render(
    <RouterProvider
      router={router}
      flushSync={(callback) => {
        flushSync(callback);
      }}
    />,
  );

  const from = screen.getByLabelText('From', { exact: true });
  const to = screen.getByLabelText('To', { exact: true });
  act(() => {
    fireEvent.change(from, { target: { value: '2026-09-01' } });
    fireEvent.change(to, { target: { value: '2026-09-19' } });
  });

  const params = new URLSearchParams(router.state.location.search);
  expect(params.get('date_from')).toBe('2026-09-01');
  expect(params.get('date_to')).toBe('2026-09-19');
  expect(params.get('user_id')).toBe('U1');
  expect(from).toHaveValue('2026-09-01');
  expect(to).toHaveValue('2026-09-19');
});
