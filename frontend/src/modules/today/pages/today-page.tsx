import { useState } from 'react';
import { Link } from 'react-router';

import {
  EmptyState,
  ErrorState,
  PageHeader,
  StatCard,
} from '@/common/components/page';
import { SlackText } from '@/common/components/slack-text';
import { Badge } from '@/common/components/ui/badge';
import { Button } from '@/common/components/ui/button';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';
import { formatDate } from '@/common/lib/format';

import { useToday } from '../hooks';
import { TodaySkeleton } from '../loading';
import { answeredSummary } from '../today-utils';

export default function TodayPage() {
  const [allResponses, setAllResponses] = useState(false);
  const [allBlocked, setAllBlocked] = useState(false);

  const query = useToday();
  const data = query.data;
  const hour = new Date().getHours();

  return (
    <div className="page">
      <PageHeader
        title={
          hour < 12
            ? 'Good morning'
            : hour < 18
              ? 'Good afternoon'
              : 'Good evening'
        }
        description={
          data
            ? formatDate(data.date, {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
              })
            : "Your team's day at a glance."
        }
      />
      {query.isPending ? (
        <TodaySkeleton />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        data && (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <StatCard
                label="Answered"
                value={answeredSummary(data.counts).value}
                description={answeredSummary(data.counts).description}
              />
              <StatCard
                label="Still to answer"
                value={data.counts.awaiting}
                description={
                  data.counts.awaiting
                    ? 'Waiting on them'
                    : 'Everyone has replied'
                }
              />
              <StatCard
                label="Blocked"
                value={
                  <span
                    className={data.counts.blocked ? 'text-destructive' : ''}
                  >
                    {data.counts.blocked}
                  </span>
                }
                description={
                  data.counts.blocked ? 'Needs attention' : 'Nothing reported'
                }
              />
            </div>
            {data.blocked.length > 0 && (
              <Card className="ring-destructive/30">
                <CardHeader>
                  <CardTitle className="text-destructive">
                    Blocked right now
                  </CardTitle>
                </CardHeader>
                <CardContent className="divide-y">
                  {(allBlocked ? data.blocked : data.blocked.slice(0, 6)).map(
                    (row, index) => (
                      <div key={`${row.user_id}-${index}`} className="py-3">
                        <div className="font-medium">
                          {row.real_name || row.user_id}
                        </div>
                        <div className="mt-1 text-sm text-muted-foreground">
                          <SlackText text={row.blockers} />
                        </div>
                      </div>
                    ),
                  )}
                  {data.blocked.length > 6 && !allBlocked && (
                    <Button variant="ghost" onClick={() => setAllBlocked(true)}>
                      Show all {data.blocked.length} blockers
                    </Button>
                  )}
                </CardContent>
              </Card>
            )}
            <div className="grid items-start gap-6 lg:grid-cols-[1.5fr_1fr]">
              <Card>
                <CardHeader>
                  <CardTitle>This morning</CardTitle>
                </CardHeader>
                <CardContent>
                  {!data.responses.length ? (
                    <EmptyState
                      title="No answers yet"
                      description="When your team replies to the bot, their answers appear here."
                    />
                  ) : (
                    <div className="divide-y">
                      {(allResponses
                        ? data.responses
                        : data.responses.slice(0, 10)
                      ).map((row, index) => (
                        <div key={`${row.user_id}-${index}`} className="py-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">
                              {row.real_name || row.user_id}
                            </span>
                            {row.has_blockers && (
                              <Badge variant="destructive">Blocked</Badge>
                            )}
                            {row.mood && (
                              <span
                                className="ml-auto text-sm"
                                aria-label={`Mood: ${row.mood}`}
                              >
                                {row.mood}
                              </span>
                            )}
                          </div>
                          <p className="mt-1 text-sm text-muted-foreground">
                            <SlackText text={row.today || row.yesterday} />
                          </p>
                        </div>
                      ))}
                      {data.responses.length > 10 && !allResponses && (
                        <Button
                          variant="ghost"
                          onClick={() => setAllResponses(true)}
                        >
                          Show all {data.responses.length} answers
                        </Button>
                      )}
                    </div>
                  )}
                  {data.awaiting.length > 0 && (
                    <div className="mt-4 border-t pt-4">
                      <h3 className="mb-2 text-xs font-medium text-muted-foreground">
                        Still to answer · {data.awaiting.length}
                      </h3>
                      <div className="flex flex-wrap gap-1.5">
                        {data.awaiting.map((row) => (
                          <Badge variant="secondary" key={row.user_id}>
                            {row.real_name || row.user_id}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
              <div className="space-y-6">
                <Card>
                  <CardHeader>
                    <CardTitle>Recent recognition</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {data.kudos.length ? (
                      <div className="divide-y">
                        {data.kudos.map((row) => (
                          <div key={row.id} className="py-3">
                            <p className="text-sm">
                              <strong>{row.from_name || row.from_user}</strong>{' '}
                              thanked{' '}
                              <strong>{row.to_name || row.to_user}</strong>
                            </p>
                            <p className="mt-1 text-sm text-muted-foreground">
                              <SlackText text={row.message} />
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <EmptyState
                        title="Nothing yet this week"
                        description="Kudos given in Slack show up here."
                      />
                    )}
                  </CardContent>
                </Card>
                {data.next_chat && (
                  <Card>
                    <CardHeader>
                      <CardTitle
                        className={data.next_chat.overdue ? 'text-warning' : ''}
                      >
                        {data.next_chat.overdue
                          ? 'Coffee chat overdue'
                          : 'Next coffee chat'}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <Link
                        className="font-medium hover:underline"
                        to={`/dashboard/connect/${data.next_chat.program_id}`}
                      >
                        {data.next_chat.name}
                      </Link>
                      <p className="mt-2 text-sm text-muted-foreground">
                        {data.next_chat.overdue
                          ? 'Was due '
                          : data.next_chat.days_away === 0
                            ? 'Today · '
                            : data.next_chat.days_away === 1
                              ? 'Tomorrow · '
                              : `In ${data.next_chat.days_away} days · `}
                        {formatDate(data.next_chat.date)}
                        {data.next_chat.overdue ? ' and has not run' : ''}
                      </p>
                    </CardContent>
                  </Card>
                )}
              </div>
            </div>
          </>
        )
      )}
    </div>
  );
}
