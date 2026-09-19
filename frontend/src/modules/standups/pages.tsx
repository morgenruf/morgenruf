import {
  Children,
  cloneElement,
  isValidElement,
  useId,
  useState,
  type ReactNode,
} from 'react';
import { AlarmClock, CalendarDays, Plus, Trash, Users, X } from 'lucide-react';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { useSearchParams } from 'react-router';
import { toast } from 'sonner';

import { errorMessage } from '@/common/api/errors';
import { usePermissions } from '@/common/auth/use-session';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
} from '@/common/components/page';
import { Badge } from '@/common/components/ui/badge';
import { Button } from '@/common/components/ui/button';
import { Card, CardContent } from '@/common/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/common/components/ui/dialog';
import { Input } from '@/common/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/common/components/ui/select';
import { applyApiErrors } from '@/common/forms/api-errors';

import {
  healthLabel,
  sortedStandups,
  standupDefaults,
  validTimezone,
  weekdays,
} from './form-utils';
import {
  useStandupHealth,
  useStandupMutations,
  useStandupResources,
  useStandups,
  type Standup,
  type StandupInput,
} from './hooks';

function Field({
  label,
  children,
  help,
}: {
  label: string;
  children: ReactNode;
  help?: string;
}) {
  const id = useId();

  return (
    <div className="grid gap-2 text-sm font-medium">
      <label htmlFor={id}>{label}</label>
      {Children.map(children, (child, index) =>
        index === 0 &&
        isValidElement<{ id?: string; 'aria-describedby'?: string }>(child)
          ? cloneElement(child, {
              id,
              'aria-describedby': help ? `${id}-help` : undefined,
            })
          : child,
      )}
      {help && (
        <p
          id={`${id}-help`}
          className="text-xs font-normal text-muted-foreground"
        >
          {help}
        </p>
      )}
    </div>
  );
}

const reminderOptions = [
  { value: 0, label: 'No reminder' },
  { value: 30, label: '30 minutes' },
  { value: 60, label: '1 hour' },
  { value: 120, label: '2 hours' },
  { value: 180, label: '3 hours' },
  { value: 240, label: '4 hours' },
  { value: 480, label: '8 hours' },
  { value: 960, label: '16 hours' },
  { value: 1200, label: '20 hours' },
  { value: -1, label: 'The weekend (~2.5 days)' },
];
const groupOptions = [
  { value: 'member', label: 'Member' },
  { value: 'question', label: 'Question' },
];
const editWindowOptions = [
  { value: 'report', label: 'Until report time' },
  { value: '4h', label: '4 hours' },
  { value: 'none', label: 'No limit' },
];
const aiProviderOptions = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
];

const tabs = ['Basics', 'Schedule', 'Summary', 'Advanced'] as const;

function StandupEditor({
  standup,
  close,
}: {
  standup?: Standup;
  close: () => void;
}) {
  const id = useId();
  const [tab, setTab] = useState<(typeof tabs)[number]>('Basics');
  const [templateGallery, setTemplateGallery] = useState(false);
  const [memberSearch, setMemberSearch] = useState('');

  const form = useForm<StandupInput>({
    defaultValues: standupDefaults(standup),
  });
  const {
    register,
    setValue,
    handleSubmit,
    formState: { errors },
  } = form;

  const values = useWatch({ control: form.control });
  const resources = useStandupResources(values.channel_id);
  const { save } = useStandupMutations();

  const participants = values.participants ?? [];
  const questions = values.questions ?? [];
  const days = values.schedule_days ?? [];

  const onSubmit = handleSubmit(
    async (body) => {
      if (!body.schedule_days?.length) {
        setTab('Schedule');
        form.setError('schedule_days', { message: 'Choose at least one day.' });

        return;
      }

      if (!validTimezone(body.schedule_tz ?? '')) {
        setTab('Schedule');
        form.setError('schedule_tz', { message: 'Choose a valid timezone.' });

        return;
      }

      if (!body.questions?.some((q) => q.trim())) {
        setTab('Schedule');
        form.setError('questions', { message: 'Add at least one question.' });

        return;
      }

      try {
        await save.mutateAsync({
          id: standup?.id,
          body: { ...body, questions: body.questions.filter((q) => q.trim()) },
        });
        toast.success(standup ? 'Standup updated' : 'Standup created');
        close();
      } catch (error) {
        applyApiErrors(error, form.setError);
      }
    },
    (invalid) => {
      if (invalid.channel_id || invalid.name) setTab('Basics');
      else if (invalid.schedule_time || invalid.schedule_tz) setTab('Schedule');
    },
  );

  const channels = (resources.channels.data ?? []).map((channel) => ({
    value: channel.id,
    label: `#${channel.name}`,
  }));
  const channelOptions = [
    { value: '', label: 'Choose a channel…' },
    ...channels,
  ];
  const reportChannelOptions = [
    { value: '', label: 'Same as standup channel' },
    ...channels,
  ];

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{standup ? 'Edit standup' : 'New standup'}</DialogTitle>
          <DialogDescription>
            Choose who takes part, when they are asked, and how answers are
            shared.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-6">
          <div
            role="tablist"
            aria-label="Standup settings"
            className="flex gap-1 overflow-x-auto border-b pb-3"
          >
            {tabs.map((name, index) => (
              <Button
                key={name}
                id={`${id}-${name}`}
                role="tab"
                type="button"
                aria-selected={tab === name}
                aria-controls={`${id}-panel-${name}`}
                tabIndex={tab === name ? 0 : -1}
                variant={tab === name ? 'secondary' : 'ghost'}
                onClick={() => setTab(name)}
                onKeyDown={(event) => {
                  if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
                    event.preventDefault();

                    const next =
                      tabs[
                        (index + (event.key === 'ArrowRight' ? 1 : 3)) %
                          tabs.length
                      ];

                    setTab(next);
                    document.getElementById(`${id}-${next}`)?.focus();
                  }
                }}
              >
                {name}
              </Button>
            ))}
          </div>
          <section
            role="tabpanel"
            aria-labelledby={`${id}-Basics`}
            id={`${id}-panel-Basics`}
            hidden={tab !== 'Basics'}
            className="space-y-5"
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Standup name">
                <Input {...register('name', { required: 'Enter a name.' })} />
              </Field>
              <Controller
                control={form.control}
                name="channel_id"
                rules={{ required: 'Choose a channel.' }}
                render={({ field, fieldState }) => (
                  <Select
                    name={field.name}
                    value={field.value}
                    items={channelOptions}
                    disabled={save.isPending}
                    onValueChange={(value) => {
                      if (value !== null) field.onChange(value);
                    }}
                  >
                    <Field label="Channel">
                      <SelectTrigger
                        className="w-full"
                        ref={field.ref}
                        onBlur={field.onBlur}
                        aria-invalid={fieldState.invalid}
                      >
                        <SelectValue />
                      </SelectTrigger>
                    </Field>
                    <SelectContent>
                      {channelOptions.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
            {errors.channel_id && (
              <p role="alert" className="text-sm text-destructive">
                {errors.channel_id.message}
              </p>
            )}
            <fieldset className="space-y-3">
              <legend className="mb-2 text-sm font-medium">Participants</legend>
              <p className="text-sm text-muted-foreground">
                Leave everyone unselected to include the whole channel.
              </p>
              <Input
                placeholder="Search participants…"
                aria-label="Search participants"
                value={memberSearch}
                onChange={(event) => setMemberSearch(event.target.value)}
              />
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setValue(
                      'participants',
                      resources.members.data?.map((member) => member.id) ?? [],
                    )
                  }
                >
                  Select all
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setValue('participants', [])}
                >
                  Use whole channel
                </Button>
              </div>
              {resources.members.isPending ? (
                <LoadingState />
              ) : resources.members.error ? (
                <ErrorState
                  error={resources.members.error}
                  retry={() => resources.members.refetch()}
                />
              ) : (
                <div className="grid max-h-52 gap-2 overflow-y-auto rounded-lg border p-3 sm:grid-cols-2">
                  {resources.members.data
                    ?.filter((member) =>
                      `${member.name} ${member.id}`
                        .toLowerCase()
                        .includes(memberSearch.toLowerCase()),
                    )
                    .map((member) => (
                      <label
                        key={member.id}
                        className="flex items-center gap-2 text-sm"
                      >
                        <input
                          type="checkbox"
                          className="size-4 accent-primary"
                          checked={participants.includes(member.id)}
                          onChange={(event) =>
                            setValue(
                              'participants',
                              event.target.checked
                                ? [...participants, member.id]
                                : participants.filter(
                                    (value) => value !== member.id,
                                  ),
                              { shouldDirty: true },
                            )
                          }
                        />
                        {member.name || member.id}
                      </label>
                    ))}
                </div>
              )}
              <p className="text-xs text-muted-foreground">
                {participants.length
                  ? `${participants.length} selected`
                  : 'Everyone in the channel'}
              </p>
            </fieldset>
          </section>
          <section
            role="tabpanel"
            aria-labelledby={`${id}-Schedule`}
            id={`${id}-panel-Schedule`}
            hidden={tab !== 'Schedule'}
            className="space-y-5"
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Time">
                <Input
                  type="time"
                  {...register('schedule_time', { required: 'Set a time.' })}
                />
              </Field>
              <Field label="Timezone">
                <Input list={`${id}-timezones`} {...register('schedule_tz')} />
                <datalist id={`${id}-timezones`}>
                  {['UTC', ...Intl.supportedValuesOf('timeZone')].map(
                    (zone) => (
                      <option key={zone}>{zone}</option>
                    ),
                  )}
                </datalist>
              </Field>
            </div>
            {errors.schedule_tz && (
              <p role="alert" className="text-sm text-destructive">
                {errors.schedule_tz.message}
              </p>
            )}
            <fieldset>
              <legend className="mb-2 text-sm font-medium">Days</legend>
              <div className="flex flex-wrap gap-2">
                {weekdays.map((day) => (
                  <Button
                    key={day}
                    type="button"
                    size="sm"
                    variant={days.includes(day) ? 'default' : 'outline'}
                    aria-pressed={days.includes(day)}
                    onClick={() =>
                      setValue(
                        'schedule_days',
                        days.includes(day)
                          ? days.filter((value) => value !== day)
                          : [...days, day],
                        { shouldDirty: true },
                      )
                    }
                  >
                    {day[0].toUpperCase() + day.slice(1)}
                  </Button>
                ))}
              </div>
              {errors.schedule_days && (
                <p role="alert" className="mt-2 text-sm text-destructive">
                  {errors.schedule_days.message}
                </p>
              )}
            </fieldset>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium">Questions</h3>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setTemplateGallery(!templateGallery)}
                >
                  Use a template
                </Button>
              </div>
              {templateGallery && (
                <div className="grid max-h-64 gap-2 overflow-y-auto sm:grid-cols-2">
                  {resources.templates.data?.map((template) => (
                    <button
                      key={template.id}
                      type="button"
                      className="rounded-lg border p-3 text-left hover:bg-muted"
                      onClick={() => {
                        setValue('questions', template.questions ?? [], {
                          shouldDirty: true,
                        });
                        setTemplateGallery(false);
                      }}
                    >
                      <span className="font-medium">
                        {template.icon} {template.name}
                      </span>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {template.description}
                      </p>
                    </button>
                  ))}
                  {resources.templates.error && (
                    <ErrorState
                      error={resources.templates.error}
                      retry={() => resources.templates.refetch()}
                    />
                  )}
                </div>
              )}
              {questions.map((_, index) => (
                <div key={index} className="flex gap-2">
                  <Input
                    aria-label={`Question ${index + 1}`}
                    {...register(`questions.${index}`)}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove question ${index + 1}`}
                    onClick={() =>
                      setValue(
                        'questions',
                        questions.filter((_, position) => position !== index),
                      )
                    }
                  >
                    <X className="size-4" />
                  </Button>
                </div>
              ))}
              {errors.questions && (
                <p role="alert" className="text-sm text-destructive">
                  {errors.questions.message}
                </p>
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setValue('questions', [...questions, ''])}
              >
                <Plus className="size-4" />
                Add question
              </Button>
            </div>
            <Controller
              control={form.control}
              name="reminder_minutes"
              render={({ field, fieldState }) => (
                <Select
                  name={field.name}
                  value={field.value}
                  items={reminderOptions}
                  disabled={save.isPending}
                  onValueChange={(value) => {
                    if (value !== null) field.onChange(value);
                  }}
                >
                  <Field label="Remind participants before standup">
                    <SelectTrigger
                      className="w-full"
                      ref={field.ref}
                      onBlur={field.onBlur}
                      aria-invalid={fieldState.invalid}
                    >
                      <SelectValue />
                    </SelectTrigger>
                  </Field>
                  <SelectContent>
                    {reminderOptions.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </section>
          <section
            role="tabpanel"
            aria-labelledby={`${id}-Summary`}
            id={`${id}-panel-Summary`}
            hidden={tab !== 'Summary'}
            className="space-y-5"
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <Controller
                control={form.control}
                name="report_channel"
                render={({ field, fieldState }) => (
                  <Select
                    name={field.name}
                    value={field.value}
                    items={reportChannelOptions}
                    disabled={save.isPending}
                    onValueChange={(value) => {
                      if (value !== null) field.onChange(value);
                    }}
                  >
                    <Field label="Report channel">
                      <SelectTrigger
                        className="w-full"
                        ref={field.ref}
                        onBlur={field.onBlur}
                        aria-invalid={fieldState.invalid}
                      >
                        <SelectValue />
                      </SelectTrigger>
                    </Field>
                    <SelectContent>
                      {reportChannelOptions.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
              <Field label="Report time">
                <Input type="time" {...register('report_time')} />
              </Field>
              <Field
                label="Daily email to"
                help="This standup’s answers, sent after its reporting window."
              >
                <Input
                  type="email"
                  placeholder="lead@company.com"
                  {...register('digest_email')}
                />
              </Field>
              <Field label="Remind missing participants before report (minutes)">
                <Input
                  type="number"
                  min={5}
                  max={120}
                  step={5}
                  {...register('nudge_minutes_before', {
                    valueAsNumber: true,
                    min: 5,
                    max: 120,
                  })}
                />
              </Field>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" {...register('digest_enabled')} />
              Send that email daily
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" {...register('nudge_missing')} />
              Privately remind people who have not answered
            </label>
            <p className="text-xs text-muted-foreground">
              People on leave and those who have skipped today are left alone.
            </p>
          </section>
          <section
            role="tabpanel"
            aria-labelledby={`${id}-Advanced`}
            id={`${id}-panel-Advanced`}
            hidden={tab !== 'Advanced'}
            className="space-y-5"
          >
            <div className="space-y-3">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" {...register('post_to_thread')} />
                Post answers as a Slack thread
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" {...register('post_summary')} />
                Post a daily summary to the channel
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" {...register('notify_on_report')} />
                Mention participants when the report posts
              </label>
            </div>
            <Controller
              control={form.control}
              name="group_by"
              render={({ field, fieldState }) => (
                <Select
                  name={field.name}
                  value={field.value}
                  items={groupOptions}
                  disabled={save.isPending}
                  onValueChange={(value) => {
                    if (value !== null) field.onChange(value);
                  }}
                >
                  <Field label="Group report by">
                    <SelectTrigger
                      className="w-full"
                      ref={field.ref}
                      onBlur={field.onBlur}
                      aria-invalid={fieldState.invalid}
                    >
                      <SelectValue />
                    </SelectTrigger>
                  </Field>
                  <SelectContent>
                    {groupOptions.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
            <div className="rounded-lg border bg-muted/30 p-4">
              <h3 className="mb-1 font-medium">Shared workspace settings</h3>
              <p className="mb-4 text-xs text-muted-foreground">
                These settings apply to every standup in this workspace.
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                <Controller
                  control={form.control}
                  name="edit_window"
                  render={({ field, fieldState }) => (
                    <Select
                      name={field.name}
                      value={field.value}
                      items={editWindowOptions}
                      disabled={save.isPending}
                      onValueChange={(value) => {
                        if (value !== null) field.onChange(value);
                      }}
                    >
                      <Field label="Edit window">
                        <SelectTrigger
                          className="w-full"
                          ref={field.ref}
                          onBlur={field.onBlur}
                          aria-invalid={fieldState.invalid}
                        >
                          <SelectValue />
                        </SelectTrigger>
                      </Field>
                      <SelectContent>
                        {editWindowOptions.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
                <Field label="Jira base URL">
                  <Input
                    type="url"
                    placeholder="https://yourteam.atlassian.net"
                    {...register('jira_base_url')}
                  />
                </Field>
                <Field label="GitHub repository">
                  <Input placeholder="org/repo" {...register('github_repo')} />
                </Field>
                <Field label="Linear team prefix">
                  <Input placeholder="ENG" {...register('linear_team')} />
                </Field>
                <Controller
                  control={form.control}
                  name="ai_provider"
                  render={({ field, fieldState }) => (
                    <Select
                      name={field.name}
                      value={field.value}
                      items={aiProviderOptions}
                      disabled={save.isPending}
                      onValueChange={(value) => {
                        if (value !== null) field.onChange(value);
                      }}
                    >
                      <Field label="AI provider">
                        <SelectTrigger
                          className="w-full"
                          ref={field.ref}
                          onBlur={field.onBlur}
                          aria-invalid={fieldState.invalid}
                        >
                          <SelectValue />
                        </SelectTrigger>
                      </Field>
                      <SelectContent>
                        {aiProviderOptions.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" {...register('ai_summary_enabled')} />
                  Enable AI-generated daily summary
                </label>
              </div>
              <p className="mt-3 text-xs text-muted-foreground">
                An API key for the chosen AI provider must be configured on the
                server.
              </p>
            </div>
          </section>
          {Object.entries(errors)
            .filter(([field]) => field !== 'root')
            .map(
              ([field, error]) =>
                typeof error?.message === 'string' && (
                  <p
                    role="alert"
                    key={field}
                    className="text-sm text-destructive"
                  >
                    {field.replaceAll('_', ' ')}: {error.message}
                  </p>
                ),
            )}
          {errors.root && (
            <p
              role="alert"
              className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive"
            >
              {errors.root.message ?? errors.root.server?.message}
            </p>
          )}
          <div className="flex justify-end gap-2 border-t pt-4">
            <Button type="button" variant="outline" onClick={close}>
              Cancel
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? 'Saving…' : 'Save standup'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function StandupsPage() {
  const query = useStandups();
  const health = useStandupHealth();
  const { channels } = useStandupResources();
  const { save, remove } = useStandupMutations();

  const { canAdminister } = usePermissions();
  const editable = canAdminister('standup');

  const [params, setParams] = useSearchParams();
  const selected = params.get('edit');
  const creating = params.get('new') === 'true';
  const editing = query.data?.find((item) => String(item.id) === selected);

  const close = () =>
    setParams((previous) => {
      previous.delete('edit');
      previous.delete('new');

      return previous;
    });

  return (
    <div className="page">
      <PageHeader
        title="Standups"
        description="A little structure for a calmer workday."
        actions={
          editable && (
            <Button onClick={() => setParams({ new: 'true' })}>
              <Plus className="size-4" />
              New standup
            </Button>
          )
        }
      />
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => query.refetch()} />
      ) : !query.data?.length ? (
        <EmptyState
          title="Your first standup starts here"
          description="Choose a channel, a few questions, and a time that works for your team."
          action={
            editable && (
              <Button onClick={() => setParams({ new: 'true' })}>
                Create standup
              </Button>
            )
          }
        />
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {query.data.length}{' '}
            {query.data.length === 1 ? 'standup' : 'standups'} · earliest time
            of day first
          </p>
          {sortedStandups(query.data).map((standup) => {
            const channel = channels.data?.find(
              (value) => value.id === standup.channel_id,
            );

            const metrics = health.data?.schedules?.find(
              (row) => row.schedule_id === standup.id,
            );

            return (
              <Card key={standup.id}>
                <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start">
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <AlarmClock className="size-5" />
                  </div>
                  <div className="min-w-0 flex-1 space-y-3">
                    <div className="flex flex-wrap items-center gap-3">
                      <h2 className="font-semibold">{standup.name}</h2>
                      <Badge variant={standup.active ? 'default' : 'secondary'}>
                        {standup.active ? 'Active' : 'Paused'}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      #{channel?.name ?? standup.channel_id} ·{' '}
                      {standup.schedule_time} {standup.schedule_tz}
                    </p>
                    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                      <span className="inline-flex items-center gap-1">
                        <Users className="size-3.5" />
                        {standup.participants?.length
                          ? `${standup.participants.length} participants`
                          : 'Everyone in the channel'}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <CalendarDays className="size-3.5" />
                        {standup.schedule_days.join(', ')}
                      </span>
                    </div>
                    {standup.registration_error ? (
                      <p
                        role="alert"
                        className="rounded-md bg-destructive/10 p-3 text-sm text-destructive"
                      >
                        <strong>This standup never runs.</strong>{' '}
                        {standup.registration_error}
                      </p>
                    ) : (
                      <>
                        {standup.next_run && (
                          <p className="text-xs text-muted-foreground">
                            Next run:{' '}
                            {new Date(standup.next_run).toLocaleString()}
                          </p>
                        )}
                        {metrics && (
                          <p className="text-xs">
                            <span className="font-medium">
                              {healthLabel(metrics.completion_rate)}
                              {metrics.completion_rate != null
                                ? ` · ${metrics.completion_rate}%`
                                : ''}
                            </span>
                            <span className="text-muted-foreground">
                              {' '}
                              · {metrics.completed} of {metrics.expected} filed
                              in the last 14 days
                            </span>
                          </p>
                        )}
                      </>
                    )}
                  </div>
                  {editable && (
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={save.isPending}
                        onClick={() =>
                          save.mutate(
                            {
                              id: standup.id,
                              body: { active: !standup.active },
                            },
                            {
                              onError: (error) =>
                                toast.error(errorMessage(error)),
                            },
                          )
                        }
                      >
                        {standup.active ? 'Pause' : 'Resume'}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setParams({ edit: String(standup.id) })}
                      >
                        Edit
                      </Button>
                      <Button
                        size="icon-sm"
                        variant="destructiveGhost"
                        disabled={remove.isPending}
                        onClick={() => {
                          if (
                            window.confirm(
                              `Delete ${standup.name}? This cannot be undone.`,
                            )
                          )
                            remove.mutate(standup.id, {
                              onSuccess: () => toast.success('Standup deleted'),
                              onError: (error) =>
                                toast.error(errorMessage(error)),
                            });
                        }}
                      >
                        <Trash />
                        <span className="sr-only">Delete</span>
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
      {editable && (creating || editing) && (
        <StandupEditor
          key={editing?.id ?? 'new'}
          standup={editing}
          close={close}
        />
      )}
    </div>
  );
}

export default StandupsPage;
