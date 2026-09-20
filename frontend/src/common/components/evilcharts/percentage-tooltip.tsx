import { formatDate } from '@/common/lib/format';

import { ChartTooltipSurface } from './ui/recharts-tooltip';

export function PercentageTooltip({
  active,
  point,
}: {
  active?: boolean;
  point?: { date: string; rate: number | null };
}) {
  if (!active || !point) return null;

  return (
    <ChartTooltipSurface>
      <p className="font-medium">{formatDate(point.date)}</p>
      <p className="flex items-center justify-between gap-5">
        <span className="text-muted-foreground">Completion</span>
        <span className="font-semibold tabular-nums">
          {point.rate === null ? 'Not scheduled' : `${point.rate}%`}
        </span>
      </p>
    </ChartTooltipSurface>
  );
}
