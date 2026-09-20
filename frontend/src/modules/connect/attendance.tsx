import { useId, useState } from 'react';
import {
  CalendarCheck,
  ChevronDown,
  ChevronRight,
  Coffee,
  MessageCircle,
  TrendingUp,
} from 'lucide-react';

import type { useMemberDirectory } from '@/common/api/use-member-directory';
import {
  SkeletonPeople,
  SkeletonRegion,
  SkeletonTable,
} from '@/common/components/loading-skeleton';
import { LoadingTransition } from '@/common/components/loading-transition';
import { EmptyState, ErrorState, StatCard } from '@/common/components/page';
import { Person } from '@/common/components/person';
import { Badge } from '@/common/components/ui/badge';
import { Button } from '@/common/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';
import { ScrollArea } from '@/common/components/ui/scroll-area';

import { AttendanceChart } from './attendance-chart';
import {
  attendanceColors,
  attendanceLabels,
  attendanceOutcomes,
  attendanceRate,
} from './form-utils';
import { useAttendance, useRoundMatches } from './hooks';
import { AttendanceSkeleton } from './loading';

function RoundMatches({
  roundId,
  person,
}: {
  roundId: number;
  person: ReturnType<typeof useMemberDirectory>['person'];
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
              <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2">
                {match.members.map((userId) => (
                  <Person key={userId} {...person(userId)} size="compact" />
                ))}
              </div>
              <span className="flex flex-wrap gap-2">
                {match.agreed_at && (
                  <Badge variant="outline">
                    Agreed {new Date(match.agreed_at).toLocaleString()}
                  </Badge>
                )}
                {match.has_zoom && <Badge variant="outline">Zoom</Badge>}
                <Badge
                  variant="secondary"
                  className={attendanceColors[match.status]}
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
  const id = useId();

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

    const people = showAll
      ? participation.data
      : participation.data?.slice(0, 12);

    return (
      <section aria-label="Coffee chat attendance" className="space-y-5">
        <p className="text-xs text-muted-foreground">
          Summary of the latest available rounds, up to 10.
        </p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Answered pairings that met"
            value={rate == null ? 'No outcomes yet' : `${rate}%`}
            description={`${totals.matches} ${totals.matches === 1 ? 'introduction' : 'introductions'} across ${rounds.data.length} ${rounds.data.length === 1 ? 'round' : 'rounds'}`}
            icon={TrendingUp}
            tone="primary"
          />
          <StatCard
            label="Met"
            value={totals.met}
            description={
              <span className={totals.missed ? 'text-warning' : undefined}>
                {totals.missed} did not meet
              </span>
            }
            icon={Coffee}
            tone="success"
          />
          <StatCard
            label="No reply"
            value={totals.no_reply}
            description="Unknown, rather than a miss"
            icon={MessageCircle}
            tone="neutral"
          />
          <StatCard
            label="Agreed a time"
            value={totals.agreed}
            description={
              <span
                className={totals.undelivered ? 'text-destructive' : undefined}
              >
                {totals.undelivered} introductions not delivered
              </span>
            }
            icon={CalendarCheck}
            tone="primary"
          />
        </div>
        <AttendanceChart rounds={rounds.data} />
        <div className="grid gap-5 xl:grid-cols-2">
          <Card className="min-w-0">
            <CardHeader>
              <CardTitle>Pairings</CardTitle>
              <CardDescription>
                Open a round to see who was paired and whether they met.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="divide-y rounded-lg border">
                {rounds.data.map((round) => (
                  <div key={round.id}>
                    <button
                      type="button"
                      className="flex w-full items-start gap-2 rounded-lg px-3 py-4 text-left hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                      aria-expanded={open === round.id}
                      aria-controls={`${id}-round-${round.id}`}
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
                          {attendanceOutcomes.map(
                            (status) =>
                              round[status] > 0 && (
                                <Badge
                                  key={status}
                                  variant="secondary"
                                  className={attendanceColors[status]}
                                >
                                  {round[status]}{' '}
                                  {attendanceLabels[status].toLowerCase()}
                                </Badge>
                              ),
                          )}
                        </span>
                      </span>
                    </button>
                    <div
                      id={`${id}-round-${round.id}`}
                      hidden={open !== round.id}
                    >
                      {open === round.id && (
                        <RoundMatches
                          roundId={round.id}
                          person={members.person}
                        />
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
          <Card className="min-w-0">
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
                    <SkeletonTable columns={5} />
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
                    <ScrollArea orientation="horizontal" className="min-w-0">
                      <table className="w-full text-sm">
                        <caption className="sr-only">
                          Participation over the last 6 rounds
                        </caption>
                        <thead>
                          <tr className="border-b text-left text-xs text-muted-foreground">
                            <th className="py-3 font-medium">Person</th>
                            <th className="px-2 py-3 font-medium">Paired</th>
                            <th className="px-2 py-3 font-medium">Met</th>
                            <th className="px-2 py-3 font-medium">
                              Did not meet
                            </th>
                            <th className="px-2 py-3 font-medium">No reply</th>
                          </tr>
                        </thead>
                        <tbody>
                          {people?.map((person) => (
                            <tr
                              key={person.user_id}
                              className="border-b last:border-0"
                            >
                              <td className="py-3 pr-3">
                                <Person
                                  {...members.person(person.user_id)}
                                  detail={
                                    person.last_met
                                      ? `Last met ${new Date(person.last_met).toLocaleDateString()}`
                                      : undefined
                                  }
                                />
                              </td>
                              <td className="px-2 py-3 tabular-nums">
                                {person.paired}
                              </td>
                              <td className="px-2 py-3 tabular-nums text-success">
                                {person.met}
                              </td>
                              <td className="px-2 py-3 tabular-nums text-warning">
                                {person.missed}
                              </td>
                              <td className="px-2 py-3 tabular-nums text-muted-foreground">
                                {person.no_reply}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </ScrollArea>
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
