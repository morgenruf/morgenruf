import { LoadingTransition } from '@/common/components/loading-transition';
import { EmptyState, ErrorState, PageHeader } from '@/common/components/page';
import { Person } from '@/common/components/person';
import { SlackText } from '@/common/components/slack-text';
import { Badge } from '@/common/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';
import { formatDate, relativeTime } from '@/common/lib/format';

import { useInsights } from '../hooks';
import { InsightsSkeleton } from '../loading';

export default function InsightsPage() {
  const { query, members } = useInsights();

  return (
    <div className="page">
      <PageHeader
        title="Insights"
        description="Patterns that deserve a closer look, across the last 30 days."
      />
      <LoadingTransition pending={query.isPending}>
        {query.isPending ? (
          <InsightsSkeleton />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          query.data && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Showing up, without recognition</CardTitle>
                  <CardDescription>
                    People contributing standups who have received little or no
                    kudos.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {query.data.unrecognised.length ? (
                    <div className="divide-y">
                      {query.data.unrecognised.map((row) => (
                        <div
                          key={row.user_id}
                          className="flex flex-wrap items-center gap-3 py-3"
                        >
                          <div className="mr-auto">
                            <Person
                              {...members.person(row.user_id, row.real_name)}
                            />
                          </div>
                          <Badge variant="secondary">
                            {row.standups} standups
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            Last filed{' '}
                            {relativeTime(row.last_standup).toLowerCase()}
                          </span>
                          <Badge variant="outline">
                            {row.kudos ? `${row.kudos} kudos` : 'No kudos'}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      title="Everyone has been recognised"
                      description="Everyone who showed up has been thanked by someone."
                    />
                  )}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Persistent blockers</CardTitle>
                  <CardDescription>
                    Blockers repeated over at least three days.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {query.data.stuck.length ? (
                    <div className="divide-y">
                      {query.data.stuck.map((row, index) => (
                        <div key={`${row.user_id}-${index}`} className="py-4">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <Person
                              {...members.person(row.user_id, row.real_name)}
                            />
                            <Badge variant="destructive">{row.days} days</Badge>
                          </div>
                          <p className="mt-3 text-sm text-muted-foreground">
                            <SlackText text={row.text} />
                          </p>
                          <p className="mt-2 text-xs text-muted-foreground">
                            Since {formatDate(row.first_seen)} · Last mentioned{' '}
                            {relativeTime(row.last_seen).toLowerCase()}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      title="No persistent blockers"
                      description="Nobody is repeating a blocker. Nothing to chase."
                    />
                  )}
                </CardContent>
              </Card>
            </>
          )
        )}
      </LoadingTransition>
    </div>
  );
}
