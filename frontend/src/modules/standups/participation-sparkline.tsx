import {
  healthColors,
  type HealthTone,
} from '@/common/components/evilcharts/chart-palette';
import { EvilLineChart } from '@/common/components/evilcharts/charts/recharts-line-chart';

export function ParticipationSparkline({
  series,
  tone,
}: {
  series: (number | null)[];
  tone: HealthTone;
}) {
  const data = series.map((value, index) => ({
    index,
    rate:
      value === null || !Number.isFinite(value)
        ? null
        : Math.min(100, Math.max(0, value)),
  }));

  return (
    <div aria-hidden="true" className="h-7 w-20 shrink-0">
      <EvilLineChart
        data={data}
        config={{
          rate: { label: 'Participation', colors: healthColors(tone) },
        }}
        className="h-full w-full aspect-auto"
        chartProps={{
          accessibilityLayer: false,
          margin: { top: 4, right: 4, bottom: 4, left: 4 },
        }}
      >
        <EvilLineChart.XAxis dataKey="index" hide />
        <EvilLineChart.YAxis domain={[0, 100]} hide />
        <EvilLineChart.Line
          dataKey="rate"
          glowing
          connectNulls={false}
          lineProps={{ activeDot: false }}
        >
          <EvilLineChart.Dot variant="default" />
        </EvilLineChart.Line>
      </EvilLineChart>
    </div>
  );
}
