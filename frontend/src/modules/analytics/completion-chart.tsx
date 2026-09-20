import { completionColors } from '@/common/components/evilcharts/chart-palette';
import { EvilAreaChart } from '@/common/components/evilcharts/charts/recharts-area-chart';
import { PercentageTooltip } from '@/common/components/evilcharts/percentage-tooltip';
import { ChartTooltip } from '@/common/components/evilcharts/ui/recharts-tooltip';
import { formatDate } from '@/common/lib/format';

const config = { rate: { label: 'Completion', colors: completionColors } };

export function CompletionChart({
  data,
}: {
  data: { date: string; rate: number | null }[];
}) {
  return (
    <div
      role="group"
      aria-label="Completion percentage by day, from 0 to 100 percent"
    >
      <EvilAreaChart
        data={data}
        config={config}
        curveType="monotone"
        className="h-64 w-full min-w-0 aspect-auto"
        chartProps={{ margin: { top: 12, right: 12, bottom: 4, left: 0 } }}
      >
        <EvilAreaChart.Grid stroke="var(--border)" />
        <EvilAreaChart.XAxis
          dataKey="date"
          padding={{ left: 8, right: 8 }}
          tickFormatter={(date) =>
            formatDate(date, { day: 'numeric', month: 'short' })
          }
          minTickGap={24}
        />
        <EvilAreaChart.YAxis
          domain={[0, 100]}
          ticks={[0, 25, 50, 75, 100]}
          tickFormatter={(value) => `${value}%`}
          width={44}
        />
        <ChartTooltip
          filterNull={false}
          cursor={{ stroke: 'var(--muted-foreground)', strokeDasharray: '3 3' }}
          content={({ active, label }) => (
            <PercentageTooltip
              active={active}
              point={data.find((point) => point.date === label)}
            />
          )}
        />
        <EvilAreaChart.Area
          dataKey="rate"
          variant="gradient"
          strokeVariant="solid"
          connectNulls={false}
        >
          <EvilAreaChart.Dot variant="default" />
          <EvilAreaChart.ActiveDot variant="colored-border" />
        </EvilAreaChart.Area>
      </EvilAreaChart>
    </div>
  );
}
