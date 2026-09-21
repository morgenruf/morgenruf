import { EvilBarChart } from '@/common/components/evilcharts/charts/recharts-bar-chart';
import { PercentageTooltip } from '@/common/components/evilcharts/percentage-tooltip';
import { ChartTooltip } from '@/common/components/evilcharts/ui/recharts-tooltip';

const config = {
  plottedRate: { label: 'Completion', colors: { light: ['var(--success)'] } },
};

export function DailyTrendChart({
  series,
  dates,
  name,
}: {
  series: (number | null)[];
  dates: string[];
  name: string;
}) {
  const data = series.map((rate, index) => ({
    date: dates[index],
    rate,
    // Unscheduled days keep a neutral baseline marker, never a failure color.
    plottedRate: rate === null ? 0 : Math.min(100, Math.max(0, rate)),
    color:
      rate === null
        ? 'var(--muted-foreground)'
        : rate >= 70
          ? 'var(--success)'
          : rate >= 40
            ? 'var(--warning)'
            : 'var(--destructive)',
  }));

  return (
    <div role="group" aria-label={`${name} daily completion trend`}>
      <EvilBarChart
        data={data}
        config={config}
        className="h-8 w-32 min-w-32 aspect-auto"
        barCategoryGap="12%"
        barRadius={2}
        chartProps={{ margin: { top: 1, right: 0, bottom: 0, left: 0 } }}
      >
        <EvilBarChart.XAxis dataKey="date" hide />
        <EvilBarChart.YAxis domain={[0, 100]} hide />
        <EvilBarChart.Bar
          dataKey="plottedRate"
          colorKey="color"
          variant="gradient"
          barProps={{ minPointSize: 2 }}
        />
        <ChartTooltip
          cursor={false}
          escapeClipping
          content={({ active, label }) => (
            <PercentageTooltip
              active={active}
              point={data.find((point) => point.date === label)}
            />
          )}
        />
      </EvilBarChart>
    </div>
  );
}
