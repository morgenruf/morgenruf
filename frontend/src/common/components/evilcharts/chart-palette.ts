import type { ChartConfig } from './ui/recharts-chart';

export type HealthTone = 'success' | 'warning' | 'destructive';

// CSS variables follow the current theme without remounting animated charts.
export function healthColors(tone: HealthTone): ChartConfig[string]['colors'] {
  return {
    light: [
      `var(--${tone})`,
      `color-mix(in srgb, var(--${tone}) 65%, var(--foreground))`,
    ],
  };
}

export const completionColors = {
  light: ['var(--chart-1)', 'var(--chart-2)'],
};
