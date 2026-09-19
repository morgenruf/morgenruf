import { useParams } from 'react-router';

import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
} from '@/common/components/page';
import { SlackText } from '@/common/components/slack-text';
import { ThemeToggle } from '@/common/components/theme-toggle';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';
import { formatDate } from '@/common/lib/format';

import { usePublicFeed } from '../hooks';

export default function FeedPage() {
  const { token = '' } = useParams();
  const query = usePublicFeed(token);

  return (
    <div className="page max-w-3xl">
      <header className="flex items-center justify-between">
        <a
          href="/dashboard/login"
          className="flex items-center gap-2 font-semibold"
        >
          <img
            src="/static/icon-192.png"
            alt=""
            className="size-8 rounded-md"
          />
          Morgenruf
        </a>
        <ThemeToggle />
      </header>
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        query.data && (
          <>
            <PageHeader
              title={query.data.title || 'Standup report'}
              description={formatDate(query.data.date)}
            />
            {query.data.standups.length ? (
              query.data.standups.map((row, index) => (
                <Card key={`${row.user_id}-${index}`}>
                  <CardHeader>
                    <CardTitle>{row.user_name || row.user_id}</CardTitle>
                    {row.submitted_at && (
                      <p className="text-xs text-muted-foreground">
                        Submitted{' '}
                        {formatDate(row.submitted_at, {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </p>
                    )}
                  </CardHeader>
                  <CardContent className="grid gap-5 sm:grid-cols-2">
                    {[
                      ['Yesterday', row.yesterday],
                      ['Today', row.today],
                      ['Blockers', row.blockers],
                    ].map(([label, text]) => (
                      <div
                        key={label}
                        className={label === 'Blockers' ? 'sm:col-span-2' : ''}
                      >
                        <h3
                          className={`mb-1 text-xs font-medium ${label === 'Blockers' && row.has_blockers ? 'text-destructive' : 'text-muted-foreground'}`}
                        >
                          {label}
                        </h3>
                        <div className="text-sm">
                          <SlackText text={text} />
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              ))
            ) : (
              <EmptyState
                title="No responses yet"
                description="Standup responses will appear here when the team submits them."
              />
            )}
          </>
        )
      )}
    </div>
  );
}
