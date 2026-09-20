import { useEffect, useMemo, useState } from 'react';
import { Download } from 'lucide-react';
import { useSearchParams } from 'react-router';
import { toast } from 'sonner';

import { errorMessage } from '@/common/api/errors';
import type { StandupResponse } from '@/common/api/generated/data-contracts';
import { useSession } from '@/common/auth/use-session';
import { LoadingField } from '@/common/components/loading-skeleton';
import { LoadingTransition } from '@/common/components/loading-transition';
import { EmptyState, ErrorState, PageHeader } from '@/common/components/page';
import { Person } from '@/common/components/person';
import { SlackText } from '@/common/components/slack-text';
import { Badge } from '@/common/components/ui/badge';
import { Button } from '@/common/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';
import { Input } from '@/common/components/ui/input';
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
import { formatDate } from '@/common/lib/format';

import { exportReports, useReports } from '../hooks';
import { ReportsSkeleton } from '../loading';

export default function ReportsPage() {
  const { data: session } = useSession();
  const [params, setParams] = useSearchParams();
  const dateFrom = params.get('date_from') ?? '';
  const dateTo = params.get('date_to') ?? '';
  const userId = params.get('user_id') ?? '';

  const [dayLimit, setDayLimit] = useState(7);
  const [allParticipation, setAllParticipation] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [exporting, setExporting] = useState(false);

  const invalidRange = Boolean(dateFrom && dateTo && dateFrom > dateTo);
  const filters = {
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    user_id: userId || undefined,
  };
  const { reports, members } = useReports(filters, !invalidRange);

  const names = useMemo(
    () =>
      Object.fromEntries(
        (members.data ?? []).map((member) => [
          member.id,
          member.name || member.display_name || member.id,
        ]),
      ),
    [members.data],
  );

  const grouped = useMemo(() => {
    const groups = new Map<string, StandupResponse[]>();

    for (const row of reports.data?.standups ?? []) {
      const date =
        row.standup_date || row.submitted_at?.slice(0, 10) || 'Unknown';
      groups.set(date, [...(groups.get(date) ?? []), row]);
    }

    return [...groups].sort(([a], [b]) => b.localeCompare(a));
  }, [reports.data]);

  useEffect(() => {
    setDayLimit(7);
    setExpanded(new Set());
    setAllParticipation(false);
  }, [dateFrom, dateTo, userId]);

  function filter(name: string, value: string) {
    // Keep controlled inputs in sync before another edit reads the URL filters.
    setParams(
      (current) => {
        const next = new URLSearchParams(current);

        if (value) next.set(name, value);
        else next.delete(name);

        return next;
      },
      { flushSync: true },
    );
  }

  function preset(days: number) {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - days + 1);

    const iso = (date: Date) =>
      `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set('date_from', iso(start));
        next.set('date_to', iso(end));

        return next;
      },
      { flushSync: true },
    );
  }

  async function exportCsv() {
    setExporting(true);

    try {
      const exported = await exportReports({
        from: dateFrom || undefined,
        to: dateTo || undefined,
      });

      const blob = new Blob([exported], {
        type: 'text/csv;charset=utf-8',
      });
      const url = URL.createObjectURL(blob);

      const link = document.createElement('a');
      link.href = url;
      link.download = `standups-${session?.team_id ?? 'workspace'}.csv`;
      link.click();

      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setExporting(false);
    }
  }

  const memberOptions = [
    { value: '', label: 'All members' },
    ...(members.data ?? []).map((member) => ({
      value: member.id,
      label: member.name || member.display_name || member.id,
    })),
  ];

  return (
    <div className="page">
      <PageHeader
        title="Reports"
        reserveActionSpace
        description="Standup history, filtered by date or member."
        actions={
          <Button
            variant="outline"
            onClick={() => void exportCsv()}
            disabled={exporting || invalidRange}
          >
            <Download className="size-4" />
            {exporting ? 'Exporting…' : 'Export CSV'}
          </Button>
        }
      />
      <Card>
        <CardContent className="grid gap-4 pt-1 sm:grid-cols-3">
          <div className="field">
            <Label htmlFor="report-from">From</Label>
            <Input
              id="report-from"
              type="date"
              value={dateFrom}
              max={dateTo || undefined}
              onChange={(event) => filter('date_from', event.target.value)}
            />
          </div>
          <div className="field">
            <Label htmlFor="report-to">To</Label>
            <Input
              id="report-to"
              type="date"
              value={dateTo}
              min={dateFrom || undefined}
              onChange={(event) => filter('date_to', event.target.value)}
            />
          </div>
          <div className="field">
            <Label htmlFor="report-member">Member</Label>
            <LoadingField
              pending={members.isPending}
              label="Loading member filter…"
            >
              <Select
                items={memberOptions}
                value={userId}
                onValueChange={(value) => filter('user_id', value ?? '')}
              >
                <SelectTrigger
                  id="report-member"
                  className="min-h-9 w-full data-[size=default]:h-auto *:data-[slot=select-value]:line-clamp-none"
                >
                  <SelectValue className="min-w-0">
                    {userId ? (
                      <Person {...members.person(userId)} size="compact" />
                    ) : (
                      'All members'
                    )}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {memberOptions.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.value ? (
                        <Person
                          {...members.person(item.value)}
                          size="compact"
                        />
                      ) : (
                        item.label
                      )}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </LoadingField>
          </div>
          <div className="flex flex-wrap gap-2 sm:col-span-3">
            <Button variant="outline" size="sm" onClick={() => preset(7)}>
              Last 7 days
            </Button>
            <Button variant="outline" size="sm" onClick={() => preset(30)}>
              Last 30 days
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setParams({}, { flushSync: true })}
            >
              Reset filters
            </Button>
            <span className="ml-auto text-xs text-muted-foreground">
              CSV exports all members in the selected dates.
            </span>
          </div>
        </CardContent>
      </Card>
      {invalidRange ? (
        <p role="alert" className="text-sm text-destructive">
          The start date must be on or before the end date.
        </p>
      ) : (
        <LoadingTransition pending={reports.isPending}>
          {reports.isPending ? (
            <ReportsSkeleton />
          ) : reports.error ? (
            <ErrorState
              error={reports.error}
              retry={() => void reports.refetch()}
            />
          ) : (
            reports.data && (
              <>
                <Card>
                  <CardHeader>
                    <CardTitle>Participation</CardTitle>
                    <CardDescription>
                      {reports.data.total_days} days in this window
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {reports.data.participation.length ? (
                      <>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Member</TableHead>
                              <TableHead>Answered</TableHead>
                              <TableHead>Participation</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {(allParticipation
                              ? reports.data.participation
                              : reports.data.participation.slice(0, 10)
                            ).map((row) => (
                              <TableRow key={row.user_id}>
                                <TableCell>
                                  <Person
                                    {...members.person(row.user_id, row.name)}
                                  />
                                </TableCell>
                                {!row.expected ? (
                                  <TableCell
                                    colSpan={2}
                                    className="text-muted-foreground"
                                  >
                                    {row.enrolled === false
                                      ? 'Not in any standup'
                                      : row.on_vacation
                                        ? 'On vacation'
                                        : 'Nothing scheduled in this window'}
                                  </TableCell>
                                ) : (
                                  <>
                                    <TableCell className="tabular-nums">
                                      {row.responses}/{row.total}
                                    </TableCell>
                                    <TableCell>
                                      <span
                                        aria-label={`${Math.max(0, Math.min(row.stars, 5))} out of 5 stars`}
                                        className="text-warning"
                                      >
                                        {'★'.repeat(
                                          Math.max(0, Math.min(row.stars, 5)),
                                        )}
                                        {'☆'.repeat(
                                          5 -
                                            Math.max(0, Math.min(row.stars, 5)),
                                        )}
                                      </span>
                                    </TableCell>
                                  </>
                                )}
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                        {reports.data.participation.length > 10 &&
                          !allParticipation && (
                            <Button
                              variant="ghost"
                              className="mt-3"
                              onClick={() => setAllParticipation(true)}
                            >
                              Show all {reports.data.participation.length}{' '}
                              members
                            </Button>
                          )}
                      </>
                    ) : (
                      <EmptyState title="No participation data" />
                    )}
                  </CardContent>
                </Card>
                {!grouped.length ? (
                  <EmptyState
                    title="No responses in this window"
                    description="Try another date range or member."
                  />
                ) : (
                  grouped.slice(0, dayLimit).map(([date, rows]) => (
                    <Card key={date}>
                      <CardHeader>
                        <CardTitle>{formatDate(date)}</CardTitle>
                        <CardDescription>
                          {rows.length}{' '}
                          {rows.length === 1 ? 'response' : 'responses'}
                        </CardDescription>
                      </CardHeader>
                      <CardContent className="divide-y">
                        {(expanded.has(date) ? rows : rows.slice(0, 5)).map(
                          (row, index) => (
                            <article
                              key={`${row.id ?? row.user_id}-${index}`}
                              className="py-5 first:pt-0"
                            >
                              <div className="flex flex-wrap items-center gap-3">
                                <Person
                                  {...members.person(
                                    row.user_id,
                                    row.real_name || row.user_name,
                                  )}
                                  detail={
                                    row.submitted_at
                                      ? formatDate(row.submitted_at, {
                                          hour: '2-digit',
                                          minute: '2-digit',
                                        })
                                      : undefined
                                  }
                                />
                                {row.mood && (
                                  <Badge variant="secondary">{row.mood}</Badge>
                                )}
                                {row.has_blockers && (
                                  <Badge variant="destructive">Blocked</Badge>
                                )}
                              </div>
                              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                                {[row.yesterday, row.today, row.blockers].map(
                                  (answer, index) => (
                                    <div
                                      key={index}
                                      className={
                                        index === 2 ? 'sm:col-span-2' : ''
                                      }
                                    >
                                      <h3
                                        className={`mb-1 text-xs font-medium ${index === 2 && row.has_blockers ? 'text-destructive' : 'text-muted-foreground'}`}
                                      >
                                        {row.questions?.[index] ||
                                          ['Yesterday', 'Today', 'Blockers'][
                                            index
                                          ]}
                                      </h3>
                                      <div className="text-sm leading-relaxed">
                                        <SlackText
                                          text={answer}
                                          members={names}
                                          channels={reports.data?.channel_names}
                                        />
                                      </div>
                                    </div>
                                  ),
                                )}
                              </div>
                            </article>
                          ),
                        )}
                        {rows.length > 5 && !expanded.has(date) && (
                          <Button
                            variant="ghost"
                            className="mt-3"
                            onClick={() =>
                              setExpanded(
                                (current) => new Set([...current, date]),
                              )
                            }
                          >
                            Show all {rows.length} responses
                          </Button>
                        )}
                      </CardContent>
                    </Card>
                  ))
                )}
                {grouped.length > dayLimit && (
                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={() => setDayLimit((current) => current + 7)}
                  >
                    Load earlier days ({grouped.length - dayLimit} remaining)
                  </Button>
                )}
              </>
            )
          )}
        </LoadingTransition>
      )}
    </div>
  );
}
