import { useSearchParams } from 'react-router';

import { useMemberDirectory } from '@/common/api/use-member-directory';
import { LoadingField } from '@/common/components/loading-skeleton';
import { LoadingTransition } from '@/common/components/loading-transition';
import {
  EmptyState,
  ErrorState,
  PageHeader,
  StatCard,
} from '@/common/components/page';
import { Person } from '@/common/components/person';
import { Badge } from '@/common/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';
import { Checkbox } from '@/common/components/ui/checkbox';
import { Label } from '@/common/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/common/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/common/components/ui/table';
import { Tabs, TabsList, TabsTrigger } from '@/common/components/ui/tabs';
import { formatDate, relativeTime } from '@/common/lib/format';

import { analyticsView, rateTone } from '../analytics-utils';
import { CompletionChart } from '../completion-chart';
import { DailyTrendChart } from '../daily-trend-chart';
import { useAnalytics } from '../hooks';
import { AnalyticsSkeleton } from '../loading';

export default function AnalyticsPage() {
  const [params, setParams] = useSearchParams();
  const days = params.get('days') === '30' ? 30 : 7;
  const scheduleId = params.get('schedule') ?? '';
  const includeUnenrolled = params.get('unenrolled') === 'true';

  const query = useAnalytics(days);
  const directory = useMemberDirectory();
  const data = query.data;
  const view = data ? analyticsView(data, scheduleId, includeUnenrolled) : null;

  const scheduleOptions = [
    { value: '', label: 'All standups' },
    ...(data?.schedules ?? []).map((schedule) => ({
      value: String(schedule.schedule_id),
      label: schedule.name,
    })),
  ];

  function filter(key: string, value: string) {
    setParams((current) => {
      const next = new URLSearchParams(current);

      if (value) next.set(key, value);
      else next.delete(key);

      return next;
    });
  }

  return (
    <div className="page page-wide">
      <PageHeader
        title="Analytics"
        description="Participation, blockers, and standup health."
        actions={
          <Tabs
            value={days}
            onValueChange={(value) => filter('days', String(value))}
          >
            <TabsList aria-label="Analytics time range">
              {[7, 30].map((value) => (
                <TabsTrigger key={value} value={value}>
                  {value} days
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        }
      />
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <LoadingField
            pending={query.isPending}
            label="Loading standup filter…"
            className="w-56"
          >
            <Select
              items={scheduleOptions}
              value={scheduleId}
              onValueChange={(value) => filter('schedule', value ?? '')}
            >
              <SelectTrigger
                id="analytics-schedule"
                aria-label="Standup"
                className="w-56"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {scheduleOptions.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </LoadingField>
        </div>
        <Label className="flex items-center gap-2">
          <Checkbox
            checked={includeUnenrolled}
            onCheckedChange={(checked) =>
              filter('unenrolled', checked ? 'true' : '')
            }
          />
          Include unenrolled
        </Label>
      </div>
      <LoadingTransition pending={query.isPending}>
        {query.isPending ? (
          <AnalyticsSkeleton />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          data &&
          view && (
            <>
              {!data.members.length ? (
                <EmptyState
                  title="No analytics yet"
                  description="Participation will appear once your team starts submitting standups."
                />
              ) : (
                <>
                  <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                    <StatCard
                      label="Completion rate"
                      value={
                        <span
                          className={rateTone(view.expected ? view.rate : null)}
                        >
                          {view.expected ? `${Math.round(view.rate)}%` : '—'}
                        </span>
                      }
                      description={`${view.completed} of ${view.expected} expected responses`}
                    />
                    <StatCard
                      label="Responding members"
                      value={`${view.enrolled.filter((member) => member.responses > 0).length} / ${view.enrolled.length}`}
                      description={`In the last ${days} days`}
                    />
                    <StatCard
                      label="Days with blockers"
                      value={view.visible.reduce(
                        (count, member) => count + member.days_with_blockers,
                        0,
                      )}
                      description="Reported by enrolled members"
                    />
                    <StatCard
                      label="Not enrolled"
                      value={view.unenrolled.length}
                      description="Members in no active standup"
                    />
                  </div>
                  <Card>
                    <CardHeader>
                      <CardTitle>Completion over time</CardTitle>
                      <CardDescription>
                        Completed responses divided by scheduled responses.
                        Unscheduled days stay empty.
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <CompletionChart data={view.series} />
                      <details className="mt-3 text-xs text-muted-foreground">
                        <summary className="cursor-pointer">
                          View chart data
                        </summary>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Date</TableHead>
                              <TableHead>Completion</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {view.series.map((point) => (
                              <TableRow key={point.date}>
                                <TableCell>{formatDate(point.date)}</TableCell>
                                <TableCell>
                                  {point.rate === null
                                    ? 'Not scheduled'
                                    : `${point.rate}%`}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </details>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader>
                      <CardTitle>By member</CardTitle>
                      <CardDescription>
                        {view.enrolled.length} enrolled
                        {view.unenrolled.length
                          ? `, ${view.unenrolled.length} in no standup`
                          : ''}
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      {view.visible.length ? (
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Member</TableHead>
                              <TableHead>Completion</TableHead>
                              <TableHead>Answered</TableHead>
                              <TableHead>Blocker days</TableHead>
                              <TableHead>Last seen</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {view.visible.map((member) => (
                              <TableRow key={member.user_id}>
                                <TableCell>
                                  <Person
                                    {...directory.person(
                                      member.user_id,
                                      member.real_name,
                                    )}
                                  />
                                  {member.on_vacation && (
                                    <Badge variant="secondary" className="mt-1">
                                      On vacation
                                    </Badge>
                                  )}
                                </TableCell>
                                {!member.enrolled ? (
                                  <TableCell
                                    colSpan={4}
                                    className="text-muted-foreground"
                                  >
                                    Not in any standup
                                  </TableCell>
                                ) : (
                                  <>
                                    <TableCell>
                                      <span
                                        className={rateTone(
                                          member.expected
                                            ? member.completion_rate
                                            : null,
                                        )}
                                      >
                                        {member.expected
                                          ? `${member.completion_rate}%`
                                          : 'Not scheduled'}
                                      </span>
                                    </TableCell>
                                    <TableCell className="tabular-nums">
                                      {member.completed} / {member.expected}
                                    </TableCell>
                                    <TableCell>
                                      {member.days_with_blockers ? (
                                        <Badge variant="destructive">
                                          {member.days_with_blockers}
                                        </Badge>
                                      ) : (
                                        '—'
                                      )}
                                    </TableCell>
                                    <TableCell className="text-muted-foreground">
                                      {relativeTime(member.last_standup)}
                                    </TableCell>
                                  </>
                                )}
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      ) : (
                        <EmptyState title="No members match these filters" />
                      )}
                    </CardContent>
                  </Card>
                  {data.schedules.length > 0 && (
                    <Card>
                      <CardHeader>
                        <CardTitle>By standup</CardTitle>
                        <CardDescription>
                          Each standup uses its own expected schedule
                          occurrences.
                        </CardDescription>
                      </CardHeader>
                      <CardContent>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Standup</TableHead>
                              <TableHead>Members</TableHead>
                              <TableHead>Completion</TableHead>
                              <TableHead>Answered</TableHead>
                              <TableHead>Daily trend</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {data.schedules
                              .filter(
                                (schedule) =>
                                  !scheduleId ||
                                  String(schedule.schedule_id) === scheduleId,
                              )
                              .map((schedule) => (
                                <TableRow key={schedule.schedule_id}>
                                  <TableCell className="font-medium">
                                    {schedule.name}
                                  </TableCell>
                                  <TableCell>{schedule.participants}</TableCell>
                                  <TableCell
                                    className={rateTone(
                                      schedule.expected
                                        ? schedule.completion_rate
                                        : null,
                                    )}
                                  >
                                    {schedule.expected
                                      ? `${schedule.completion_rate}%`
                                      : 'Not scheduled'}
                                  </TableCell>
                                  <TableCell className="tabular-nums">
                                    {schedule.completed} / {schedule.expected}
                                  </TableCell>
                                  <TableCell>
                                    <DailyTrendChart
                                      series={schedule.series}
                                      dates={data.window_days}
                                      name={schedule.name}
                                    />
                                  </TableCell>
                                </TableRow>
                              ))}
                          </TableBody>
                        </Table>
                      </CardContent>
                    </Card>
                  )}
                  {!includeUnenrolled && view.unenrolled.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      {view.unenrolled.length} members in no standup are hidden.
                      Select “Include unenrolled” to show them.
                    </p>
                  )}
                </>
              )}
            </>
          )
        )}
      </LoadingTransition>
    </div>
  );
}
