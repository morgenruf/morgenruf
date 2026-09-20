import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import {
  SkeletonPeople,
  SkeletonRegion,
  SkeletonTable,
} from '@/common/components/loading-skeleton';
import { LoadingTransition } from '@/common/components/loading-transition';
import { EmptyState, ErrorState, StatCard } from '@/common/components/page';
import { Badge } from '@/common/components/ui/badge';
import { Button } from '@/common/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';

import { attendanceLabels, attendanceRate } from './form-utils';
import { useAttendance, useRoundMatches } from './hooks';
import { AttendanceSkeleton } from './loading';

function RoundMatches({
  roundId,
  names,
}: {
  roundId: number;
  names: Map<string, string>;
}) {
  const query = useRoundMatches(roundId);

  function renderContent() {
    if (query.isPending)
      return (
        <SkeletonRegion
          label="Loading pairings…"
          className="border-t px-4 py-3"
        >
          <SkeletonPeople rows={3} />
        </SkeletonRegion>
      );

    if (query.error)
      return <ErrorState error={query.error} retry={() => query.refetch()} />;

    return (
      <div className="space-y-2 border-t bg-muted/20 px-4 py-3">
        {query.data?.length ? (
          query.data.map((match) => (
            <div
              key={match.id}
              className="flex flex-wrap items-center justify-between gap-3 py-2 text-sm"
            >
              <span>
                {match.members
                  .map((userId) => names.get(userId) ?? userId)
                  .join(' · ')}
              </span>
              <span className="flex flex-wrap gap-2">
                {match.agreed_at && (
                  <Badge variant="outline">
                    Agreed {new Date(match.agreed_at).toLocaleString()}
                  </Badge>
                )}
                {match.has_zoom && <Badge variant="outline">Zoom</Badge>}
                <Badge
                  variant={match.status === 'met' ? 'default' : 'secondary'}
                >
                  {attendanceLabels[match.status] ?? match.status}
                </Badge>
              </span>
            </div>
          ))
        ) : (
          <p className="text-sm text-muted-foreground">
            No pairings in this round.
          </p>
        )}
      </div>
    );
  }
  return (
    <LoadingTransition pending={query.isPending}>
      {renderContent()}
    </LoadingTransition>
  );
}

export function Attendance({ programId }: { programId: number }) {
  const { rounds, participation, members } = useAttendance(programId);

  const [open, setOpen] = useState<number | null>(null);
  const [showAll, setShowAll] = useState(false);

  function renderContent() {
    if (rounds.isPending) return <AttendanceSkeleton />;

    if (rounds.error)
      return <ErrorState error={rounds.error} retry={() => rounds.refetch()} />;

    if (!rounds.data?.length)
      return (
        <EmptyState
          title="No rounds have run yet"
          description="Attendance appears here once the first introductions go out."
        />
      );

    const totals = rounds.data.reduce(
      (sum, round) => ({
        matches: sum.matches + round.matches,
        met: sum.met + round.met,
        missed: sum.missed + round.missed,
        no_reply: sum.no_reply + round.no_reply,
        undelivered: sum.undelivered + round.undelivered,
        agreed: sum.agreed + (round.agreed ?? 0),
      }),
      { matches: 0, met: 0, missed: 0, no_reply: 0, undelivered: 0, agreed: 0 },
    );
    const rate = attendanceRate(totals.met, totals.missed);

    const names = new Map(
      members.data?.map((person) => [person.id, person.name || person.id]),
    );
    const people = showAll
      ? participation.data
      : participation.data?.slice(0, 12);

    return (
      <section aria-label="Coffee chat attendance" className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Answered pairings that met"
            value={rate == null ? 'No outcomes yet' : `${rate}%`}
            description={`${totals.matches} introductions across ${rounds.data.length} rounds`}
          />
          <StatCard
            label="Met"
            value={totals.met}
            description={`${totals.missed} did not meet`}
          />
          <StatCard
            label="No reply"
            value={totals.no_reply}
            description="Unknown, rather than a miss"
          />
          <StatCard
            label="Agreed a time"
            value={totals.agreed}
            description={`${totals.undelivered} introductions not delivered`}
          />
        </div>
        <div className="grid gap-5 xl:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>By round</CardTitle>
              <CardDescription>
                Open a round to see who was paired and whether they met.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {rounds.data.length > 1 && rate != null && (
                <div
                  className="mb-5 h-56"
                  aria-label="Attendance outcomes by round"
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={[...rounds.data].reverse()}
                      margin={{ left: -20, right: 0 }}
                    >
                      <CartesianGrid vertical={false} stroke="var(--border)" />
                      <XAxis
                        dataKey="scheduled_for"
                        tickFormatter={(value) =>
                          value
                            ? new Date(value).toLocaleDateString(undefined, {
                                day: 'numeric',
                                month: 'short',
                              })
                            : '—'
                        }
                        tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                      />
                      <Tooltip
                        contentStyle={{
                          borderRadius: 8,
                          border: '1px solid var(--border)',
                          backgroundColor: 'var(--popover)',
                          color: 'var(--popover-foreground)',
                        }}
                      />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar
                        dataKey="met"
                        name="Met"
                        stackId="attendance"
                        fill="var(--chart-2)"
                      />
                      <Bar
                        dataKey="missed"
                        name="Did not meet"
                        stackId="attendance"
                        fill="var(--chart-3)"
                      />
                      <Bar
                        dataKey="no_reply"
                        name="No reply"
                        stackId="attendance"
                        fill="var(--muted-foreground)"
                      />
                      <Bar
                        dataKey="undelivered"
                        name="Not delivered"
                        stackId="attendance"
                        fill="var(--chart-4)"
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
              <div className="divide-y rounded-lg border">
                {rounds.data.map((round) => (
                  <div key={round.id}>
                    <button
                      type="button"
                      className="flex w-full items-start gap-2 px-3 py-4 text-left hover:bg-muted/50"
                      aria-expanded={open === round.id}
                      onClick={() =>
                        setOpen(open === round.id ? null : round.id)
                      }
                    >
                      {open === round.id ? (
                        <ChevronDown className="mt-0.5 size-4 shrink-0" />
                      ) : (
                        <ChevronRight className="mt-0.5 size-4 shrink-0" />
                      )}
                      <span className="min-w-0 flex-1">
                        <span className="text-sm font-medium">
                          {round.scheduled_for
                            ? new Date(round.scheduled_for).toLocaleString()
                            : 'Unscheduled'}
                        </span>
                        <span className="mt-1 block text-xs text-muted-foreground">
                          {round.matches} pairings
                          {round.rematch_requests
                            ? ` · ${round.rematch_requests} requested a new match`
                            : ''}
                        </span>
                        <span className="mt-2 flex flex-wrap gap-1">
                          {(
                            [
                              'met',
                              'missed',
                              'no_reply',
                              'undelivered',
                            ] as const
                          ).map(
                            (status) =>
                              round[status] > 0 && (
                                <Badge key={status} variant="secondary">
                                  {round[status]}{' '}
                                  {attendanceLabels[status].toLowerCase()}
                                </Badge>
                              ),
                          )}
                        </span>
                      </span>
                    </button>
                    {open === round.id && (
                      <RoundMatches roundId={round.id} names={names} />
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>By person</CardTitle>
              <CardDescription>
                The last 6 rounds, starting with the fewest meetings.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <LoadingTransition pending={participation.isPending}>
                {participation.isPending ? (
                  <SkeletonRegion label="Loading participation…">
                    <SkeletonTable columns={3} />
                  </SkeletonRegion>
                ) : participation.error ? (
                  <ErrorState
                    error={participation.error}
                    retry={() => participation.refetch()}
                  />
                ) : !participation.data?.length ? (
                  <EmptyState title="Nobody has been paired yet" />
                ) : (
                  <>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b text-left text-xs text-muted-foreground">
                            <th className="py-3 font-medium">Person</th>
                            <th className="px-2 py-3 font-medium">Paired</th>
                            <th className="px-2 py-3 font-medium">Met</th>
                            <th className="px-2 py-3 font-medium">Missed</th>
                            <th className="px-2 py-3 font-medium">No reply</th>
                          </tr>
                        </thead>
                        <tbody>
                          {people?.map((person) => (
                            <tr
                              key={person.user_id}
                              className="border-b last:border-0"
                            >
                              <td className="py-3">
                                {names.get(person.user_id) ?? person.user_id}
                                {person.last_met && (
                                  <p className="text-xs text-muted-foreground">
                                    Last met{' '}
                                    {new Date(
                                      person.last_met,
                                    ).toLocaleDateString()}
                                  </p>
                                )}
                              </td>
                              <td className="px-2 py-3 tabular-nums">
                                {person.paired}
                              </td>
                              <td className="px-2 py-3 tabular-nums">
                                {person.met}
                              </td>
                              <td className="px-2 py-3 tabular-nums">
                                {person.missed}
                              </td>
                              <td className="px-2 py-3 tabular-nums">
                                {person.no_reply}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {!showAll && participation.data.length > 12 && (
                      <Button
                        variant="ghost"
                        className="mt-3"
                        onClick={() => setShowAll(true)}
                      >
                        Show all {participation.data.length} people
                      </Button>
                    )}
                  </>
                )}
              </LoadingTransition>
              {members.error && (
                <p className="mt-3 text-xs text-muted-foreground">
                  Names are temporarily unavailable; Slack IDs are shown.
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </section>
    );
  }
  return (
    <LoadingTransition pending={rounds.isPending}>
      {renderContent()}
    </LoadingTransition>
  );
}
