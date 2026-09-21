import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ParticipationSparkline } from '../participation-sparkline';

describe('participation sparkline', () => {
  it('renders zero values and isolated points while leaving gaps at missing days', () => {
    const { container } = render(
      <ParticipationSparkline
        series={[0, 50, null, 100, null, 20, 30]}
        tone="success"
      />,
    );
    expect(
      container.querySelectorAll('.recharts-line-dots [data-chart-dot]'),
    ).toHaveLength(5);
    expect(
      container
        .querySelector('.recharts-line-curve')
        ?.getAttribute('d')
        ?.match(/M/g),
    ).toHaveLength(3);
    expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
    expect(
      container.querySelector('[role="application"]'),
    ).not.toBeInTheDocument();
  });

  it('does not plot missing or nonfinite values', () => {
    const { container } = render(
      <ParticipationSparkline
        series={[null, Number.NaN, Number.POSITIVE_INFINITY]}
        tone="warning"
      />,
    );
    expect(container.querySelectorAll('[data-chart-dot]')).toHaveLength(0);
    expect(
      container.querySelector('.recharts-line-curve'),
    ).not.toBeInTheDocument();
  });

  it('keeps gradient and glow ids independent between rows', () => {
    const { container } = render(
      <>
        <ParticipationSparkline series={[0, 100]} tone="success" />
        <ParticipationSparkline series={[0, 100]} tone="destructive" />
      </>,
    );
    const ids = [...container.querySelectorAll('[id]')].map((node) => node.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
