import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CompletionChart } from '../completion-chart';
import { DailyTrendChart } from '../daily-trend-chart';

const dates = Array.from(
  { length: 7 },
  (_, i) => `2026-09-${String(i + 1).padStart(2, '0')}`,
);

describe('analytics charts', () => {
  it('preserves zero completion and gaps with a fixed percent axis', async () => {
    const { container } = render(
      <CompletionChart
        data={[
          { date: dates[0], rate: 0 },
          { date: dates[1], rate: null },
          { date: dates[2], rate: 100 },
        ]}
      />,
    );
    expect(screen.getByText('0%')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(
      container.querySelectorAll('.recharts-area-dots [data-chart-dot]'),
    ).toHaveLength(2);
    const chart = screen.getByRole('application');
    fireEvent.focus(chart);
    fireEvent.keyDown(chart, { key: 'ArrowRight' });
    expect(await screen.findByText('Not scheduled')).toBeInTheDocument();
  });

  it('renders semantic colors at the existing health boundaries and visible zero markers', async () => {
    const { container } = render(
      <DailyTrendChart
        series={[0, 39, 40, null, 69, 70, 100]}
        dates={dates}
        name="Daily"
      />,
    );
    const colors = [...container.querySelectorAll('[id$="-point"]')].map(
      (stop) => stop.firstElementChild?.getAttribute('stop-color'),
    );
    expect(colors).toEqual([
      'var(--destructive)',
      'var(--destructive)',
      'var(--warning)',
      'var(--muted-foreground)',
      'var(--warning)',
      'var(--success)',
      'var(--success)',
    ]);
    const bars = container.querySelectorAll(
      '.recharts-bar-rectangle path[fill^="url("]',
    );
    expect(bars).toHaveLength(7);
    expect(Number(bars[0].getAttribute('height'))).toBeGreaterThan(0);
    expect(Number(bars[3].getAttribute('height'))).toBeGreaterThan(0);
    const chart = screen.getByRole('application');
    fireEvent.focus(chart);
    expect(await screen.findByText('0%')).toBeInTheDocument();
    for (let i = 0; i < 3; i++) fireEvent.keyDown(chart, { key: 'ArrowRight' });
    expect(await screen.findByText('Not scheduled')).toBeInTheDocument();
  });

  it('keeps every unscheduled day available in an all-null trend', async () => {
    const { container } = render(
      <DailyTrendChart
        series={[null, null]}
        dates={dates.slice(0, 2)}
        name="No runs"
      />,
    );
    expect(
      container.querySelectorAll('linearGradient[id$="-point"]'),
    ).toHaveLength(2);
    const chart = screen.getByRole('application');
    fireEvent.focus(chart);
    fireEvent.keyDown(chart, { key: 'ArrowRight' });
    expect(await screen.findByText('Not scheduled')).toBeInTheDocument();
  });
});
