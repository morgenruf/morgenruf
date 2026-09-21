import type { ConnectRound } from '@/common/api/generated/data-contracts';
import { healthColors } from '@/common/components/evilcharts/chart-palette';
import { EvilLineChart } from '@/common/components/evilcharts/charts/recharts-line-chart';
import {
  ChartTooltip,
  ChartTooltipSurface,
} from '@/common/components/evilcharts/ui/recharts-tooltip';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';
import { ScrollArea } from '@/common/components/ui/scroll-area';

import { attendanceTrend, roundDate } from './attendance-utils';
import {
  attendanceColors,
  attendanceLabels,
  attendanceOutcomes,
} from './form-utils';

const config = {
  rate: { label: 'Meeting rate', colors: healthColors('success') },
};

function RoundTooltip({
  active,
  round,
}: {
  active?: boolean;
  round?: ReturnType<typeof attendanceTrend>[number];
}) {
  if (!active || !round) return null;

  return (
    <ChartTooltipSurface className="min-w-48 p-3">
      <p className="font-medium">{roundDate(round.scheduled_for)}</p>
      <p className="mt-1 text-muted-foreground">
        Meeting rate:{' '}
        {round.rate == null ? 'No answered outcomes' : `${round.rate}%`}
      </p>
      <dl className="mt-3 space-y-2">
        {attendanceOutcomes.map((status) => (
          <div key={status} className="flex items-center justify-between gap-5">
            <dt className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className={`size-2 rounded-full ${attendanceColors[status]}`}
                style={{ backgroundColor: 'currentColor' }}
              />
              {attendanceLabels[status]}
            </dt>
            <dd className="tabular-nums">{round[status]}</dd>
          </div>
        ))}
      </dl>
    </ChartTooltipSurface>
  );
}

export function AttendanceChart({ rounds }: { rounds: ConnectRound[] }) {
  const data = attendanceTrend(rounds);
  const hasAnswers = data.some((round) => round.rate != null);

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>Meeting rate by round</CardTitle>
        <CardDescription>
          Latest available rounds, up to 10. Met ÷ answered pairings; rounds
          without answers remain gaps.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {hasAnswers ? (
          <div
            className="h-64 min-w-0 sm:h-72"
            role="group"
            aria-label="Meeting rate by round, from 0 to 100 percent. Exact values are available in View chart data below."
          >
            <EvilLineChart
              config={config}
              className="h-full w-full min-w-0 aspect-auto"
              data={data}
              chartProps={{
                margin: { top: 12, right: 12, bottom: 4, left: 0 },
              }}
            >
              <EvilLineChart.Grid vertical={false} stroke="var(--border)" />
              <EvilLineChart.XAxis
                dataKey="id"
                padding={{ left: 18, right: 18 }}
                tickFormatter={(id) =>
                  roundDate(
                    data.find((round) => round.id === id)?.scheduled_for ?? '',
                    true,
                  )
                }
                tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                minTickGap={24}
              />
              <EvilLineChart.YAxis
                domain={[0, 100]}
                ticks={[0, 25, 50, 75, 100]}
                tickFormatter={(value) => `${value}%`}
                tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={42}
              />
              <ChartTooltip
                filterNull={false}
                content={({ active, label }) => (
                  <RoundTooltip
                    active={active}
                    round={data.find((round) => round.id === Number(label))}
                  />
                )}
                cursor={{ stroke: 'var(--border)' }}
              />
              <EvilLineChart.Line dataKey="rate" glowing connectNulls={false}>
                <EvilLineChart.Dot variant="border" />
                <EvilLineChart.ActiveDot variant="colored-border" />
              </EvilLineChart.Line>
            </EvilLineChart>
          </div>
        ) : (
          <div className="grid min-h-48 place-content-center rounded-lg bg-muted/30 px-5 text-center">
            <p className="text-sm font-medium">No answered outcomes yet</p>
            <p className="mt-1 max-w-sm text-xs text-muted-foreground">
              Meeting rates appear once a pairing says whether they met. You can
              still explore every pairing below.
            </p>
          </div>
        )}
        <details className="mt-4 rounded-lg border">
          <summary className="cursor-pointer rounded-lg px-3 py-3 text-sm font-medium hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
            View chart data
          </summary>
          <ScrollArea
            orientation="horizontal"
            className="min-w-0 border-t px-3"
          >
            <table className="w-full text-sm">
              <caption className="sr-only">
                Meeting rates and outcomes by round, oldest first
              </caption>
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th scope="col" className="py-3 pr-3 font-medium">
                    Round
                  </th>
                  <th scope="col" className="px-2 py-3 font-medium">
                    Meeting rate
                  </th>
                  {attendanceOutcomes.map((status) => (
                    <th
                      key={status}
                      scope="col"
                      className="px-2 py-3 font-medium"
                    >
                      {attendanceLabels[status]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((round) => (
                  <tr key={round.id} className="border-b last:border-0">
                    <th scope="row" className="py-3 pr-3 text-left font-normal">
                      {roundDate(round.scheduled_for)}
                    </th>
                    <td className="px-2 py-3 tabular-nums">
                      {round.rate == null
                        ? 'No answered outcomes'
                        : `${round.rate}%`}
                    </td>
                    {attendanceOutcomes.map((status) => (
                      <td key={status} className="px-2 py-3 tabular-nums">
                        {round[status]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollArea>
        </details>
      </CardContent>
    </Card>
  );
}
