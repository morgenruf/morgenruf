import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { ConnectRound } from '@/common/api/generated/data-contracts';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';

import { attendanceTrend, roundDate } from './attendance-utils';
import {
  attendanceColors,
  attendanceLabels,
  attendanceOutcomes,
} from './form-utils';

function RoundTooltip({
  active,
  round,
}: {
  active?: boolean;
  round?: ReturnType<typeof attendanceTrend>[number];
}) {
  if (!active || !round) return null;

  return (
    <div className="min-w-48 rounded-lg border bg-popover p-3 text-xs text-popover-foreground shadow-md">
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
    </div>
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
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <LineChart
                data={data}
                margin={{ top: 12, right: 12, bottom: 4, left: 0 }}
                accessibilityLayer
              >
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis
                  dataKey="id"
                  padding={{ left: 18, right: 18 }}
                  tickFormatter={(id) =>
                    roundDate(
                      data.find((round) => round.id === id)?.scheduled_for ??
                        '',
                      true,
                    )
                  }
                  tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={24}
                />
                <YAxis
                  domain={[0, 100]}
                  ticks={[0, 25, 50, 75, 100]}
                  tickFormatter={(value) => `${value}%`}
                  tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  width={42}
                />
                <Tooltip
                  filterNull={false}
                  content={({ active, label }) => (
                    <RoundTooltip
                      active={active}
                      round={data.find((round) => round.id === Number(label))}
                    />
                  )}
                  cursor={{ stroke: 'var(--border)' }}
                />
                <Line
                  type="linear"
                  dataKey="rate"
                  name="Meeting rate"
                  stroke="var(--success)"
                  strokeWidth={2}
                  dot={{
                    r: 4,
                    fill: 'var(--success)',
                    strokeWidth: 2,
                    stroke: 'var(--card)',
                  }}
                  activeDot={{ r: 6 }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
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
          <div className="overflow-x-auto border-t px-3">
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
          </div>
        </details>
      </CardContent>
    </Card>
  );
}
