import { Fragment, useState } from 'react';
import { ChevronDown, ChevronRight, EyeOff } from 'lucide-react';

import type { Poll } from '@/common/api/generated/data-contracts';
import { useMemberDirectory } from '@/common/api/use-member-directory';
import { ConfirmDialog } from '@/common/components/confirm-dialog';
import { LoadingTransition } from '@/common/components/loading-transition';
import { EmptyState, ErrorState, PageHeader } from '@/common/components/page';
import { Badge } from '@/common/components/ui/badge';
import { Button } from '@/common/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/common/components/ui/table';
import { formatDateTime, plural } from '@/common/lib/format';

import { usePolls } from '../hooks';
import { PollsListSkeleton } from '../loading';

function percent(votes: number, total: number) {
  return total ? Math.round((votes / total) * 100) : 0;
}

function PollResults({
  poll,
  person,
}: {
  poll: Poll;
  person: (userId: string) => { name: string };
}) {
  const hidden = poll.options.every((option) => option.votes === null);

  if (hidden)
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <EyeOff className="size-4" aria-hidden />
        {plural(poll.total_votes, 'vote')} so far. Results show when the poll
        closes.
      </p>
    );

  return (
    <ul className="space-y-3" aria-label={`Results for ${poll.question}`}>
      {poll.options.map((option, index) => {
        const votes = option.votes ?? 0;
        const share = percent(votes, poll.total_votes);

        return (
          <li key={index} className="space-y-1 text-sm">
            <div className="flex items-baseline justify-between gap-3">
              <span className="min-w-0 break-words">{option.text}</span>
              <span className="shrink-0 tabular-nums text-muted-foreground">
                {votes} ({share}%)
              </span>
            </div>
            <div
              className="h-2 overflow-hidden rounded-full bg-muted"
              role="progressbar"
              aria-label={option.text}
              aria-valuenow={share}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${share}%` }}
              />
            </div>
            {!!option.voters?.length && (
              <p className="text-xs text-muted-foreground">
                {option.voters.map((id) => person(id).name).join(', ')}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export default function PollsPage() {
  const { polls, channels, close } = usePolls();
  const directory = useMemberDirectory();
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [closing, setClosing] = useState<Poll | null>(null);

  const channelName = (id: string) => {
    const channel = channels.data?.find((item) => item.id === id);
    return channel ? `#${channel.name}` : 'A channel';
  };

  const toggle = (id: number) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="page">
      <PageHeader
        title="Polls"
        description="Quick questions your team answers in Slack."
      />

      <Card>
        <CardHeader>
          <CardTitle>How it works</CardTitle>
          <CardDescription>
            Type{' '}
            <code className="rounded bg-muted px-1.5 py-0.5 text-foreground">
              /morgenruf poll
            </code>{' '}
            in any channel Morgenruf is in to open the form, or{' '}
            <code className="rounded bg-muted px-1.5 py-0.5 text-foreground">
              /morgenruf poll "Lunch?" "Pizza" "Sushi"
            </code>{' '}
            to post one straight away. Votes on an anonymous poll are stored
            without a name, and once it closes they cannot be traced back to
            anyone.
          </CardDescription>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent polls</CardTitle>
          <CardDescription>
            Polls in channels you can see in Slack, and your own.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <LoadingTransition pending={polls.isPending}>
            {polls.isPending ? (
              <PollsListSkeleton />
            ) : polls.isError ? (
              <ErrorState
                error={polls.error}
                retry={() => void polls.refetch()}
              />
            ) : !polls.data?.length ? (
              <EmptyState
                title="No polls yet"
                description="No polls yet. Type /morgenruf poll in any channel Morgenruf is in."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Question</TableHead>
                    <TableHead>Channel</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Votes</TableHead>
                    <TableHead>Closes</TableHead>
                    <TableHead>
                      <span className="sr-only">Actions</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {polls.data.map((poll) => {
                    const expanded = open.has(poll.id);
                    const Icon = expanded ? ChevronDown : ChevronRight;

                    return (
                      <Fragment key={poll.id}>
                        <TableRow>
                          <TableCell className="max-w-80 whitespace-normal">
                            <button
                              type="button"
                              className="flex items-start gap-1.5 text-left font-medium"
                              aria-expanded={expanded}
                              aria-controls={`poll-${poll.id}`}
                              onClick={() => toggle(poll.id)}
                            >
                              <Icon
                                className="mt-0.5 size-4 shrink-0"
                                aria-hidden
                              />
                              <span className="break-words">
                                {poll.question}
                              </span>
                            </button>
                          </TableCell>
                          <TableCell>{channelName(poll.channel_id)}</TableCell>
                          <TableCell>
                            <div className="flex flex-wrap gap-1">
                              <Badge
                                variant={
                                  poll.closed_at ? 'secondary' : 'default'
                                }
                              >
                                {poll.closed_at ? 'Closed' : 'Open'}
                              </Badge>
                              {poll.anonymous && (
                                <Badge variant="outline">Anonymous</Badge>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {poll.total_votes}
                          </TableCell>
                          <TableCell>
                            {poll.closed_at
                              ? formatDateTime(poll.closed_at)
                              : poll.closes_at
                                ? formatDateTime(poll.closes_at)
                                : 'When closed'}
                          </TableCell>
                          <TableCell className="text-right">
                            {poll.can_close && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => {
                                  close.reset();
                                  setClosing(poll);
                                }}
                              >
                                Close
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                        {expanded && (
                          <TableRow id={`poll-${poll.id}`}>
                            <TableCell
                              colSpan={6}
                              className="whitespace-normal"
                            >
                              <PollResults
                                poll={poll}
                                person={directory.person}
                              />
                            </TableCell>
                          </TableRow>
                        )}
                      </Fragment>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </LoadingTransition>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={!!closing}
        onOpenChange={(next) => {
          if (!next) setClosing(null);
        }}
        title="Close this poll?"
        description="Nobody can vote after this, and the results are shown to everyone in the channel."
        confirmLabel="Close poll"
        pendingLabel="Closing…"
        destructive
        pending={close.isPending}
        error={close.error}
        onConfirm={() => {
          if (closing)
            close.mutate(closing.id, { onSuccess: () => setClosing(null) });
        }}
      />
    </div>
  );
}
