import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { ConnectRound } from '@/common/api/generated/data-contracts';

import { AttendanceChart } from '../attendance-chart';
import { attendanceTrend, roundDate } from '../attendance-utils';

// EvilCharts supplies initial dimensions, so these tests exercise real Recharts.
function round(values: Partial<ConnectRound> = {}): ConnectRound {
  return {
    id: 1,
    agreed: 0,
    created_at: null,
    matches: 4,
    member_count: 8,
    met: 3,
    missed: 1,
    no_reply: 0,
    program_id: 2,
    rematch_requests: 0,
    scheduled_for: '2026-09-01T10:00:00Z',
    state: 'closed',
    team_id: 'T1',
    undelivered: 0,
    with_zoom: 0,
    ...values,
  };
}

describe('attendance chart', () => {
  it('orders rounds chronologically and leaves unanswered outcomes as gaps', () => {
    const input = [
      round({
        id: 3,
        scheduled_for: '2026-09-15T10:00:00Z',
        met: 0,
        missed: 2,
      }),
      round({ id: 1, no_reply: 5, undelivered: 2 }),
      round({
        id: 2,
        scheduled_for: '2026-09-08T10:00:00Z',
        met: 0,
        missed: 0,
        no_reply: 4,
      }),
    ];

    expect(
      attendanceTrend(input).map(({ id, rate }) => ({ id, rate })),
    ).toEqual([
      { id: 1, rate: 75 },
      { id: 2, rate: null },
      { id: 3, rate: 0 },
    ]);
    expect(input.map(({ id }) => id)).toEqual([3, 1, 2]);
  });

  it('shows a single round point on a fixed percentage axis and exposes exact outcomes', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <AttendanceChart rounds={[round({ no_reply: 2, undelivered: 1 })]} />,
    );

    expect(
      screen.getByRole('group', {
        name: /Meeting rate by round, from 0 to 100 percent/,
      }),
    ).toBeInTheDocument();
    expect(
      container.querySelectorAll('.recharts-line-dots [data-chart-dot]'),
    ).toHaveLength(1);
    expect(screen.getByText('0%')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    fireEvent.focus(screen.getByRole('application'));
    fireEvent.keyDown(screen.getByRole('application'), { key: 'ArrowRight' });
    expect(await screen.findByText('Meeting rate: 75%')).toBeInTheDocument();
    const disclosure = screen.getByText('View chart data');
    disclosure.focus();
    await user.keyboard('{Enter}');
    const table = screen.getByRole('table', {
      name: 'Meeting rates and outcomes by round, oldest first',
    });
    const row = within(table).getAllByRole('row')[1];
    expect(row).toHaveTextContent(roundDate('2026-09-01T10:00:00Z'));
    expect(
      within(row)
        .getAllByRole('cell')
        .map((cell) => cell.textContent),
    ).toEqual(['75%', '3', '1', '2', '1']);
  });

  it('does not connect the line across rounds without answers', async () => {
    const rounds = [
      round(),
      round({
        id: 2,
        scheduled_for: '2026-09-08T10:00:00Z',
        met: 0,
        missed: 0,
      }),
      round({
        id: 3,
        scheduled_for: '2026-09-15T10:00:00Z',
        met: 1,
        missed: 1,
      }),
    ];
    const { container } = render(<AttendanceChart rounds={rounds} />);
    expect(
      container.querySelectorAll('.recharts-line-dots [data-chart-dot]'),
    ).toHaveLength(2);
    expect(
      container
        .querySelector('.recharts-line-curve')
        ?.getAttribute('d')
        ?.match(/M/g),
    ).toHaveLength(2);
    await userEvent.setup().click(screen.getByText('View chart data'));
    expect(
      within(screen.getByRole('table')).getByText('No answered outcomes'),
    ).toBeInTheDocument();
  });

  it('explains an unanswered history and still offers the counts', async () => {
    const { container } = render(
      <AttendanceChart rounds={[round({ met: 0, missed: 0, no_reply: 4 })]} />,
    );
    expect(screen.getByText('No answered outcomes yet')).toBeInTheDocument();
    expect(
      container.querySelector('.recharts-surface'),
    ).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByText('View chart data'));
    const table = screen.getByRole('table');
    expect(within(table).getByText('No answered outcomes')).toBeInTheDocument();
    expect(within(table).getByText('4')).toBeInTheDocument();
  });

  it('plots a genuine zero rate and keeps it distinct from an unanswered round', async () => {
    const { container } = render(
      <AttendanceChart rounds={[round({ met: 0, missed: 4 })]} />,
    );
    expect(
      container.querySelectorAll('.recharts-line-dots [data-chart-dot]'),
    ).toHaveLength(1);
    fireEvent.focus(screen.getByRole('application'));
    expect(await screen.findByText('Meeting rate: 0%')).toBeInTheDocument();
    expect(
      screen.queryByText('No answered outcomes yet'),
    ).not.toBeInTheDocument();
  });
});
