import { Heart } from 'lucide-react';
import { useForm, useWatch } from 'react-hook-form';
import { useSearchParams } from 'react-router';
import { toast } from 'sonner';

import { useMemberDirectory } from '@/common/api/use-member-directory';
import { LoadingTransition } from '@/common/components/loading-transition';
import { EmptyState, ErrorState, PageHeader } from '@/common/components/page';
import { Person } from '@/common/components/person';
import { SlackText } from '@/common/components/slack-text';
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
import { applyApiErrors } from '@/common/forms/api-errors';
import { relativeTime } from '@/common/lib/format';

import { useKudos, type KudosConfigInput } from '../hooks';
import {
  KudosConfigSkeleton,
  KudosFeedSkeleton,
  KudosLeaderboardSkeleton,
} from '../loading';

const periodOptions = [7, 30, 90].map((days) => ({
  value: days,
  label: `Last ${days} days`,
}));

export default function KudosPage() {
  const [params, setParams] = useSearchParams();
  const days = [7, 30, 90].includes(Number(params.get('days')))
    ? Number(params.get('days'))
    : 30;

  const { feed, receivers, givers, config, save, canEdit } = useKudos(days);
  const directory = useMemberDirectory();

  const form = useForm<KudosConfigInput>({
    resetOptions: { keepDirtyValues: true },
    values: config.data
      ? {
          emoji: config.data.emoji,
          daily_allowance: config.data.daily_allowance,
        }
      : { emoji: '☕', daily_allowance: 5 },
  });

  const preview = useWatch({ control: form.control });
  const token =
    preview.emoji === ':morgenruf:' ? (
      <img
        className="inline-block size-5"
        src="/static/kudos-token-128.png"
        alt="Morgenruf token"
      />
    ) : (
      preview.emoji
    );

  return (
    <div className="page">
      <PageHeader
        title="Kudos"
        reserveActionSpace
        description="Celebrate the people who make your team better."
        actions={
          <Select
            items={periodOptions}
            value={days}
            onValueChange={(value) => {
              if (value !== null) setParams({ days: String(value) });
            }}
          >
            <SelectTrigger aria-label="Leaderboard period" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {periodOptions.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        }
      />
      <Card>
        <CardHeader>
          <CardTitle>How it works</CardTitle>
          <CardDescription>
            Send{' '}
            <code className="rounded bg-muted px-1.5 py-0.5 text-foreground">
              kudos @teammate Great work on the deploy!
            </code>{' '}
            in a DM to the bot. Everyone has{' '}
            {config.data?.daily_allowance ?? '…'} to give per day; unused kudos
            reset at midnight in each person’s timezone.
          </CardDescription>
        </CardHeader>
      </Card>
      <div className="grid gap-5 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Most recognized</CardTitle>
            <CardDescription>Teammates receiving appreciation.</CardDescription>
          </CardHeader>
          <CardContent>
            <LoadingTransition pending={receivers.isPending}>
              {receivers.isPending ? (
                <KudosLeaderboardSkeleton />
              ) : receivers.isError ? (
                <ErrorState
                  error={receivers.error}
                  retry={() => void receivers.refetch()}
                />
              ) : !receivers.data?.length ? (
                <EmptyState title="No kudos received yet" />
              ) : (
                <ol className="divide-y">
                  {receivers.data.map((person, index) => (
                    <li
                      key={person.to_user}
                      className="flex items-center gap-3 py-3 text-sm"
                    >
                      <span className="w-6 shrink-0 text-muted-foreground">
                        {index + 1}
                      </span>
                      <Person
                        className="flex-1"
                        {...directory.person(person.to_user)}
                      />
                      <span className="shrink-0 rounded-md bg-primary/10 px-2 py-1 font-medium text-primary">
                        {person.received}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </LoadingTransition>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Most encouraging</CardTitle>
            <CardDescription>
              Teammates making recognition a habit.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <LoadingTransition pending={givers.isPending}>
              {givers.isPending ? (
                <KudosLeaderboardSkeleton />
              ) : givers.isError ? (
                <ErrorState
                  error={givers.error}
                  retry={() => void givers.refetch()}
                />
              ) : !givers.data?.length ? (
                <EmptyState title="Nobody has given kudos yet" />
              ) : (
                <ol className="divide-y">
                  {givers.data.map((person, index) => (
                    <li
                      key={person.user_id}
                      className="flex items-center gap-3 py-3 text-sm"
                    >
                      <span className="w-6 shrink-0 text-muted-foreground">
                        {index + 1}
                      </span>
                      <Person
                        className="flex-1"
                        {...directory.person(person.user_id)}
                      />
                      <span className="shrink-0 rounded-md bg-primary/10 px-2 py-1 font-medium text-primary">
                        {person.given}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </LoadingTransition>
          </CardContent>
        </Card>
      </div>
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Recent appreciation</h2>
        <LoadingTransition pending={feed.isPending}>
          {feed.isPending ? (
            <KudosFeedSkeleton />
          ) : feed.isError ? (
            <ErrorState error={feed.error} retry={() => void feed.refetch()} />
          ) : !feed.data?.length ? (
            <EmptyState
              title="Give your first kudos"
              description="A quick thank-you can make someone’s day. Send one from Slack."
            />
          ) : (
            <div className="space-y-3">
              {feed.data.map((item) => (
                <Card key={item.id}>
                  <CardContent className="space-y-2 pt-4">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <Heart
                        className="size-4 shrink-0 text-primary"
                        aria-hidden="true"
                      />
                      <Person
                        size="compact"
                        {...directory.person(item.from_user, item.from_name)}
                      />
                      <span className="text-muted-foreground">thanked</span>
                      <Person
                        size="compact"
                        {...directory.person(item.to_user, item.to_name)}
                      />
                      <span className="ml-auto text-xs text-muted-foreground">
                        {relativeTime(item.created_at)}
                      </span>
                    </div>
                    <p className="whitespace-pre-wrap text-sm">
                      <SlackText text={item.message} />
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </LoadingTransition>
      </section>
      {canEdit && (
        <Card>
          <CardHeader>
            <CardTitle>The token your team gives</CardTitle>
            <CardDescription>
              Choose a token and the daily allowance. An allowance of zero
              switches giving off.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {config.isError ? (
              <ErrorState
                error={config.error}
                retry={() => void config.refetch()}
              />
            ) : (
              <LoadingTransition pending={config.isPending}>
                {config.isPending ? (
                  <KudosConfigSkeleton />
                ) : (
                  <form
                    className="space-y-4"
                    onSubmit={form.handleSubmit((data) =>
                      save.mutate(data, {
                        onSuccess: (response) => {
                          form.reset({
                            emoji: response.data.emoji,
                            daily_allowance: response.data.daily_allowance,
                          });

                          toast.success('Kudos settings saved');
                        },
                        onError: (error) =>
                          applyApiErrors(error, form.setError),
                      }),
                    )}
                  >
                    <div className="grid max-w-lg gap-4 sm:grid-cols-2">
                      <div className="space-y-2">
                        <Label htmlFor="kudos-token">
                          Emoji or Slack token
                        </Label>
                        <Input
                          id="kudos-token"
                          maxLength={16}
                          required
                          {...form.register('emoji', {
                            required: true,
                            maxLength: 16,
                          })}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="kudos-allowance">Daily allowance</Label>
                        <Input
                          id="kudos-allowance"
                          type="number"
                          min={0}
                          max={50}
                          required
                          {...form.register('daily_allowance', {
                            valueAsNumber: true,
                            min: 0,
                            max: 50,
                          })}
                        />
                      </div>
                    </div>
                    <div
                      aria-label="Kudos message preview"
                      className="max-w-lg space-y-2 rounded-lg border bg-muted/30 p-4 text-sm"
                    >
                      <p className="font-medium">
                        What your team will see in Slack
                      </p>
                      <p>
                        {token} <strong>@priya</strong> gave {token} to{' '}
                        <strong>@marcus</strong>
                      </p>
                      <p className="border-l-2 pl-3 text-muted-foreground">
                        Caught a DST bug that would have affected the whole
                        team.
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {preview.daily_allowance === 0
                          ? 'Giving is switched off'
                          : `${Math.max(0, Number(preview.daily_allowance || 0) - 1)} left today`}
                      </p>
                      {preview.emoji?.startsWith(':') &&
                        preview.emoji !== ':morgenruf:' && (
                          <p className="text-xs text-muted-foreground">
                            Slack will show this custom emoji if it exists in
                            your workspace.
                          </p>
                        )}
                    </div>
                    {Object.entries(form.formState.errors).map(
                      ([field, error]) =>
                        field !== 'root' &&
                        typeof error?.message === 'string' && (
                          <p
                            key={field}
                            role="alert"
                            className="text-sm text-destructive"
                          >
                            {error.message}
                          </p>
                        ),
                    )}
                    {form.formState.errors.root?.server && (
                      <p role="alert" className="text-sm text-destructive">
                        {form.formState.errors.root.server.message}
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      {config.data?.token_auto
                        ? 'Your token is selected automatically. Choosing a different token turns automatic selection off.'
                        : 'Your workspace uses a manually selected token.'}
                    </p>
                    <div className="flex flex-wrap items-center gap-3">
                      <Button type="submit" disabled={save.isPending}>
                        {save.isPending ? 'Saving…' : 'Save settings'}
                      </Button>
                      <a
                        href="/static/kudos-token-128.png"
                        download="morgenruf.png"
                        className="text-sm text-primary underline underline-offset-4"
                      >
                        Download Morgenruf’s Slack emoji
                      </a>
                    </div>
                  </form>
                )}
              </LoadingTransition>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
