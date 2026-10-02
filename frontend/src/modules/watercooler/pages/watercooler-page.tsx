import { useId, useMemo, useState } from 'react';
import { toast } from 'sonner';

import { errorMessage } from '@/common/api/errors';
import type {
  WatercoolerBankQuestion,
  WatercoolerChannel,
  WatercoolerChannelInput,
} from '@/common/api/generated/data-contracts';
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
import { Input } from '@/common/components/ui/input';
import { plural } from '@/common/lib/format';

import { useWatercooler } from '../hooks';
import { WatercoolerPageSkeleton } from '../loading';

const DAYS = [
  ['mon', 'Mon'],
  ['tue', 'Tue'],
  ['wed', 'Wed'],
  ['thu', 'Thu'],
  ['fri', 'Fri'],
  ['sat', 'Sat'],
  ['sun', 'Sun'],
] as const;

const PAUSED: Record<string, string> = {
  not_in_channel: 'Paused: Morgenruf is not in this channel',
  empty_pool: 'Paused: no questions left to ask',
};

function browserZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

type Draft = {
  channelId: string;
  days: string[];
  postTime: string;
  timezone: string;
  categories: string[];
  source: string;
};

function emptyDraft(categories: string[]): Draft {
  return {
    channelId: '',
    days: ['mon', 'wed', 'fri'],
    postTime: '10:00',
    timezone: browserZone(),
    categories,
    source: 'both',
  };
}

function ChannelForm({
  draft,
  setDraft,
  channelOptions,
  categories,
  editing,
  pending,
  onSave,
  onCancel,
}: {
  draft: Draft;
  setDraft: (next: Draft) => void;
  channelOptions: { id: string; name: string }[];
  categories: { key: string; label: string }[];
  editing: boolean;
  pending: boolean;
  onSave: () => void;
  onCancel: () => void;
}) {
  const id = useId();
  const toggle = (list: string[], value: string) =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

  return (
    <form
      aria-label={editing ? 'Edit channel' : 'Add a channel'}
      className="space-y-4 rounded-lg border p-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSave();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <label className="flex flex-col gap-1 text-sm font-medium">
          Channel
          <select
            className="h-9 rounded-md border bg-transparent px-2 text-sm font-normal"
            value={draft.channelId}
            disabled={editing}
            onChange={(event) =>
              setDraft({ ...draft, channelId: event.target.value })
            }
          >
            <option value="">Choose a channel…</option>
            {channelOptions.map((channel) => (
              <option key={channel.id} value={channel.id}>
                #{channel.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Time
          <Input
            type="time"
            value={draft.postTime}
            onChange={(event) =>
              setDraft({ ...draft, postTime: event.target.value })
            }
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Timezone
          <Input
            value={draft.timezone}
            onChange={(event) =>
              setDraft({ ...draft, timezone: event.target.value })
            }
          />
        </label>
      </div>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Days</legend>
        <div className="flex flex-wrap gap-3">
          {DAYS.map(([key, label]) => (
            <label key={key} className="flex items-center gap-1.5 text-sm">
              <input
                type="checkbox"
                checked={draft.days.includes(key)}
                onChange={() =>
                  setDraft({ ...draft, days: toggle(draft.days, key) })
                }
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Questions from</legend>
        <div className="flex flex-wrap gap-3">
          {(
            [
              ['both', 'Our questions and the built-in bank'],
              ['builtin', 'Built-in bank only'],
              ['custom', 'Our questions only'],
            ] as const
          ).map(([value, label]) => (
            <label key={value} className="flex items-center gap-1.5 text-sm">
              <input
                type="radio"
                name={`${id}-source`}
                checked={draft.source === value}
                onChange={() => setDraft({ ...draft, source: value })}
              />
              {label}
            </label>
          ))}
        </div>
        {draft.source !== 'custom' && (
          <div className="flex flex-wrap gap-3">
            {categories.map((category) => (
              <label
                key={category.key}
                className="flex items-center gap-1.5 text-sm"
              >
                <input
                  type="checkbox"
                  checked={draft.categories.includes(category.key)}
                  onChange={() =>
                    setDraft({
                      ...draft,
                      categories: toggle(draft.categories, category.key),
                    })
                  }
                />
                {category.label}
              </label>
            ))}
          </div>
        )}
      </fieldset>
      <div className="flex gap-2">
        <Button
          type="submit"
          disabled={
            pending ||
            !draft.channelId ||
            !draft.days.length ||
            !draft.categories.length
          }
        >
          {pending ? 'Saving…' : editing ? 'Save channel' : 'Add channel'}
        </Button>
        {editing && (
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}

function BankSection({
  bank,
  categories,
  canManage,
  onToggle,
}: {
  bank: WatercoolerBankQuestion[];
  categories: { key: string; label: string }[];
  canManage: boolean;
  onToggle: (key: string, hidden: boolean) => void;
}) {
  const [hiddenOnly, setHiddenOnly] = useState(false);
  const hiddenCount = bank.filter((q) => q.hidden).length;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Question bank</CardTitle>
        <CardDescription>
          {plural(bank.length, 'built-in question')}. Hiding one only affects
          this workspace.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={hiddenOnly}
            onChange={() => setHiddenOnly(!hiddenOnly)}
          />
          Show hidden only ({hiddenCount})
        </label>
        {categories.map((category) => {
          const items = bank.filter(
            (q) => q.category === category.key && (!hiddenOnly || q.hidden),
          );
          if (!items.length) return null;

          return (
            <section key={category.key} aria-label={category.label}>
              <h3 className="mb-2 text-sm font-semibold">{category.label}</h3>
              <ul className="divide-y rounded-lg border">
                {items.map((q) => (
                  <li
                    key={q.key}
                    className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
                  >
                    <span
                      className={
                        q.hidden ? 'text-muted-foreground line-through' : ''
                      }
                    >
                      {q.text}
                    </span>
                    {canManage ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`${q.hidden ? 'Show' : 'Hide'}: ${q.text}`}
                        onClick={() => onToggle(q.key, !q.hidden)}
                      >
                        {q.hidden ? 'Show' : 'Hide'}
                      </Button>
                    ) : (
                      q.hidden && <Badge variant="outline">Hidden</Badge>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </CardContent>
    </Card>
  );
}

export default function WatercoolerPage() {
  const {
    overview,
    channels,
    saveChannel,
    removeChannel,
    postNow,
    addQuestion,
    archiveQuestion,
    setHidden,
  } = useWatercooler();
  const data = overview.data;
  const categoryKeys = useMemo(
    () => (data?.categories ?? []).map((c) => c.key),
    [data?.categories],
  );
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState(false);
  const [newQuestion, setNewQuestion] = useState('');
  const current = draft ?? emptyDraft(categoryKeys);

  const channelName = (id: string) => {
    const channel = channels.data?.find((item) => item.id === id);
    return channel ? `#${channel.name}` : id;
  };
  const used = new Set(data?.channels.map((c) => c.channel_id));
  const channelOptions = (channels.data ?? []).filter(
    (c) => editing || !used.has(c.id),
  );

  const startEdit = (channel: WatercoolerChannel) => {
    setEditing(true);
    setDraft({
      channelId: channel.channel_id,
      days: channel.days,
      postTime: channel.post_time,
      timezone: channel.timezone,
      categories: channel.categories,
      source: channel.source,
    });
  };

  const save = () =>
    saveChannel.mutate(
      {
        channelId: current.channelId,
        body: {
          days: current.days as WatercoolerChannelInput['days'],
          post_time: current.postTime,
          timezone: current.timezone,
          source: current.source as WatercoolerChannelInput['source'],
          categories:
            current.categories as WatercoolerChannelInput['categories'],
          active: true,
        },
      },
      {
        onSuccess: () => {
          toast.success(
            `Watercooler saved for ${channelName(current.channelId)}`,
          );
          setDraft(null);
          setEditing(false);
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );

  return (
    <div className="page">
      <PageHeader
        title="Watercooler"
        description="A conversation question in a channel a few times a week. People reply in the thread."
      />
      <LoadingTransition pending={overview.isPending}>
        {overview.isPending ? (
          <WatercoolerPageSkeleton />
        ) : overview.error || !data ? (
          <ErrorState error={overview.error} retry={() => overview.refetch()} />
        ) : (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Channels</CardTitle>
                <CardDescription>
                  Nothing posts on company holidays or days off. Morgenruf has
                  to be in the channel.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {data.channels.length ? (
                  <ul
                    aria-label="Watercooler channels"
                    className="divide-y rounded-lg border"
                  >
                    {data.channels.map((channel) => (
                      <li
                        key={channel.channel_id}
                        className="flex flex-wrap items-center justify-between gap-3 px-3 py-3 text-sm"
                      >
                        <div className="space-y-1">
                          <p className="font-medium">
                            {channelName(channel.channel_id)}
                          </p>
                          <p className="text-muted-foreground">
                            {channel.days
                              .map(
                                (d) =>
                                  DAYS.find(([key]) => key === d)?.[1] ?? d,
                              )
                              .join(', ')}{' '}
                            at {channel.post_time} ({channel.timezone})
                          </p>
                          {!channel.active && (
                            <Badge variant="outline">
                              {PAUSED[channel.paused_reason ?? ''] ?? 'Paused'}
                            </Badge>
                          )}
                        </div>
                        {data.can_manage && (
                          <div className="flex flex-wrap gap-2">
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={postNow.isPending}
                              onClick={() =>
                                postNow.mutate(channel.channel_id, {
                                  onSuccess: (result) =>
                                    result.posted
                                      ? toast.success(
                                          `Posted in ${channelName(channel.channel_id)}`,
                                        )
                                      : toast.error(
                                          'Nothing was posted. Check that Morgenruf is in the channel and the module is on.',
                                        ),
                                })
                              }
                            >
                              Post one now
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => startEdit(channel)}
                            >
                              {channel.active ? 'Edit' : 'Edit and resume'}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              aria-label={`Remove ${channelName(channel.channel_id)}`}
                              disabled={removeChannel.isPending}
                              onClick={() =>
                                removeChannel.mutate(channel.channel_id)
                              }
                            >
                              Remove
                            </Button>
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState
                    title="No channels yet"
                    description="Add one below, or type /morgenruf watercooler in Slack."
                  />
                )}
                {data.can_manage && (
                  <ChannelForm
                    draft={current}
                    setDraft={setDraft}
                    channelOptions={channelOptions}
                    categories={data.categories}
                    editing={editing}
                    pending={saveChannel.isPending}
                    onSave={save}
                    onCancel={() => {
                      setDraft(null);
                      setEditing(false);
                    }}
                  />
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Our questions</CardTitle>
                <CardDescription>
                  Your own questions, mixed in with the bank unless a channel
                  asks for one or the other.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {data.questions.length ? (
                  <ul
                    aria-label="Our questions"
                    className="divide-y rounded-lg border"
                  >
                    {data.questions.map((q) => (
                      <li
                        key={q.id}
                        className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
                      >
                        <span
                          className={
                            q.archived
                              ? 'text-muted-foreground line-through'
                              : ''
                          }
                        >
                          {q.text}
                        </span>
                        {data.can_manage && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() =>
                              archiveQuestion.mutate({
                                id: q.id,
                                archived: !q.archived,
                              })
                            }
                          >
                            {q.archived ? 'Restore' : 'Archive'}
                          </Button>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No questions of your own yet.
                  </p>
                )}
                {data.can_manage && (
                  <form
                    className="flex gap-2"
                    onSubmit={(event) => {
                      event.preventDefault();
                      addQuestion.mutate(newQuestion.trim(), {
                        onSuccess: () => setNewQuestion(''),
                        onError: (error) => toast.error(errorMessage(error)),
                      });
                    }}
                  >
                    <Input
                      aria-label="New question"
                      placeholder="What is the best thing you learned this week?"
                      maxLength={300}
                      value={newQuestion}
                      onChange={(event) => setNewQuestion(event.target.value)}
                    />
                    <Button
                      type="submit"
                      disabled={
                        newQuestion.trim().length < 5 || addQuestion.isPending
                      }
                    >
                      Add
                    </Button>
                  </form>
                )}
              </CardContent>
            </Card>

            <BankSection
              bank={data.bank}
              categories={data.categories}
              canManage={data.can_manage}
              onToggle={(key, hidden) => setHidden.mutate({ key, hidden })}
            />
          </div>
        )}
      </LoadingTransition>
    </div>
  );
}
