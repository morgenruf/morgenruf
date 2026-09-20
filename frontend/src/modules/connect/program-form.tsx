import {
  Children,
  cloneElement,
  isValidElement,
  useId,
  useState,
  type ReactNode,
} from 'react';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';

import { errorMessage } from '@/common/api/errors';
import { usePermissions } from '@/common/auth/use-session';
import {
  LoadingField,
  SkeletonRegion,
  SkeletonTable,
  SkeletonText,
} from '@/common/components/loading-skeleton';
import { LoadingTransition } from '@/common/components/loading-transition';
import { EmptyState, ErrorState } from '@/common/components/page';
import { Person } from '@/common/components/person';
import { TimezoneSelect } from '@/common/components/timezone-select';
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
import { ScrollArea } from '@/common/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/common/components/ui/select';
import { applyApiErrors } from '@/common/forms/api-errors';
import { useTabbedFormValidation } from '@/common/forms/use-tabbed-form-validation';

import { dayNames, programDefaults, programTime } from './form-utils';
import {
  useConnectMutations,
  useConnectResources,
  useProgramMembers,
  type Program,
  type ProgramInput,
  type ProgramMemberInput,
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
    <div className="flex flex-col gap-2 text-sm font-medium">
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

const memberStateOptions = [
  { value: 'in', label: 'In the pool' },
  { value: 'snoozed', label: 'Snoozed 2 weeks' },
  { value: 'out', label: 'Excluded' },
];
const intervalOptions = Array.from({ length: 8 }, (_, index) => ({
  value: index + 1,
  label: index === 0 ? 'Week' : `${index + 1} weeks`,
}));
const dayOptions = dayNames.map((day, index) => ({ value: index, label: day }));
const groupSizeOptions = Array.from({ length: 7 }, (_, index) => ({
  value: index + 2,
  label: `${index + 2} people`,
}));
const introToneOptions = [
  { value: 'hybrid', label: 'Some of us are remote' },
  { value: 'remote', label: 'Fully remote' },
  { value: 'in_person', label: 'Mostly in one place' },
];
const meetingLengthOptions = [15, 30, 45, 60].map((minutes) => ({
  value: minutes,
  label: `${minutes} minutes`,
}));
const videoModeOptions = [
  { value: 'link', label: 'One shared room' },
  { value: 'zoom', label: 'A Zoom meeting each time' },
  { value: 'none', label: 'They sort it out' },
];

function ProgramMembers({ programId }: { programId: number }) {
  const query = useProgramMembers(programId);
  const { member } = useConnectMutations();
  const { canAdminister } = usePermissions();

  const [search, setSearch] = useState('');

  function renderContent() {
    if (query.isPending)
      return (
        <SkeletonRegion label="Loading coffee chat members…">
          <SkeletonTable columns={4} />
        </SkeletonRegion>
      );

    if (query.error)
      return <ErrorState error={query.error} retry={() => query.refetch()} />;

    if (!query.data?.length)
      return (
        <EmptyState
          title="Nobody in this channel yet"
          description="Invite people to the channel and they will appear here."
        />
      );

    const eligible = query.data.filter(
      (person) => person.eligible && person.state === 'in',
    ).length;

    return (
      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">
          {eligible} in the pool. Everyone in the channel is matched unless they
          are excluded, snoozed, or not eligible.
        </p>
        <Input
          aria-label="Search coffee chat members"
          placeholder="Search members…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <ScrollArea orientation="horizontal" className="min-w-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="py-3 font-medium">Member</th>
                <th className="py-3 font-medium">Paired</th>
                <th className="py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {query.data
                .filter((person) =>
                  `${person.name} ${person.user_id}`
                    .toLowerCase()
                    .includes(search.toLowerCase()),
                )
                .map((person) => (
                  <tr key={person.user_id} className="border-b last:border-0">
                    <td className="py-3 pr-3">
                      <Person
                        name={person.name || person.user_id}
                        avatar={person.avatar}
                        detail={
                          person.eligible
                            ? undefined
                            : 'Not on the eligible roster'
                        }
                      />
                    </td>
                    <td className="py-3 pr-3 tabular-nums">{person.paired}</td>
                    <td className="py-3">
                      {canAdminister('connect') ? (
                        <Select
                          items={memberStateOptions}
                          value={person.state}
                          disabled={member.isPending}
                          onValueChange={(value) =>
                            value !== null &&
                            member.mutate(
                              {
                                id: programId,
                                userId: person.user_id,
                                body: {
                                  state: value as ProgramMemberInput['state'],
                                  weeks: 2,
                                },
                              },
                              {
                                onSuccess: () =>
                                  toast.success('Participation updated'),
                                onError: (error) =>
                                  toast.error(errorMessage(error)),
                              },
                            )
                          }
                        >
                          <SelectTrigger
                            aria-label={`Status for ${person.name || person.user_id}`}
                            className="w-full"
                          >
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {memberStateOptions.map((item) => (
                              <SelectItem key={item.value} value={item.value}>
                                {item.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <Badge variant="secondary">
                          {person.state === 'in'
                            ? 'In the pool'
                            : person.state === 'out'
                              ? 'Excluded'
                              : 'Snoozed'}
                        </Badge>
                      )}
                      {person.until && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          Until {new Date(person.until).toLocaleDateString()}
                        </p>
                      )}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </ScrollArea>
      </div>
    );
  }
  return (
    <LoadingTransition pending={query.isPending}>
      {renderContent()}
    </LoadingTransition>
  );
}

function MessagePreview({ values }: { values: ProgramInput }) {
  const tone =
    values.intro_tone === 'remote'
      ? 'A call is a good way to meet someone outside your own team.'
      : values.intro_tone === 'in_person'
        ? 'A coffee or a walk is enough.'
        : 'A call or a coffee, whichever suits you.';

  const count = values.group_size ?? 2;

  return (
    <aside aria-label="Preview of the Slack message" className="space-y-3">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        What your team will see in Slack
      </p>
      <Card>
        <CardContent className="flex gap-3 p-4">
          <img
            src="/static/icon-192.png"
            alt=""
            className="size-9 rounded-lg"
          />
          <div className="min-w-0 space-y-3 text-sm">
            <p className="font-semibold">
              Morgenruf <Badge variant="secondary">APP</Badge>
            </p>
            <p>
              <span className="text-primary">@you</span> and{' '}
              <span className="text-primary">@sam</span>
              {count > 2 && ` and ${count - 2} more`} have been matched. Say
              hello right here.
            </p>
            <p>{tone}</p>
            <p className="text-xs text-muted-foreground">
              {count === 2
                ? 'Just the two of you.'
                : `${count} of you this round.`}{' '}
              {values.meeting_minutes ?? 30} minutes is plenty.
            </p>
            {values.use_icebreaker && (
              <div className="space-y-2 border-t pt-3">
                <p className="font-medium">Something to open with</p>
                <p className="border-l-2 pl-3 text-muted-foreground">
                  What is something you are proud of that nobody noticed?
                </p>
              </div>
            )}
            {values.suggest_times && (
              <div className="space-y-2">
                <p className="font-medium">Times that suit everyone’s hours</p>
                <p className="rounded-md border p-2 text-xs">
                  Friday · Amsterdam 09:00 · Kolkata 12:30
                </p>
                <span className="inline-block rounded border px-2 py-1 text-xs">
                  Works for me
                </span>
                <p className="text-xs text-muted-foreground">
                  These are suggestions. Nobody has checked your calendars.
                </p>
              </div>
            )}
            {values.video_mode === 'link' && values.meeting_link && (
              <p className="font-medium text-primary">Join the room</p>
            )}
            {values.video_mode === 'zoom' && (
              <p className="text-xs text-muted-foreground">
                A Zoom meeting is created once you agree a time.
              </p>
            )}
            <p className="border-t pt-3 text-xs text-muted-foreground">
              More options · Another starter · New match · Unavailable this
              round · Pause
            </p>
          </div>
        </CardContent>
      </Card>
      {values.post_stats && (
        <Card>
          <CardContent className="space-y-2 p-4 text-sm">
            <p className="font-medium">How the last round went</p>
            <p className="text-muted-foreground">
              5 pairs were introduced. 3 of the 4 who answered met up.
            </p>
          </CardContent>
        </Card>
      )}
      <p className="text-xs text-muted-foreground">
        Illustrative preview. Changes are only applied when you save.
      </p>
    </aside>
  );
}

export function ProgramForm({ program }: { program?: Program }) {
  const navigate = useNavigate();
  const id = useId();

  const tabs = program
    ? ['Basics', 'Matching', 'Message', 'Meeting', 'Members']
    : ['Basics', 'Matching', 'Message', 'Meeting'];
  const [tab, setTab] = useState('Basics');

  const form = useForm<ProgramInput>({
    defaultValues: programDefaults(program),
  });
  const onInvalid = useTabbedFormValidation(tabs, setTab, form.setError);
  const { register, setValue } = form;
  const values = useWatch({ control: form.control });

  const resources = useConnectResources();
  const channelOptions = [
    { value: '', label: 'Choose a channel…' },
    ...(resources.channels.data ?? []).map((channel) => ({
      value: channel.id,
      label: `#${channel.name}`,
    })),
  ];
  const { save } = useConnectMutations();
  const { canAdminister } = usePermissions();
  const editable = canAdminister('connect');

  const submit = form.handleSubmit(
    async (body) => {
      try {
        new Intl.DateTimeFormat('en', { timeZone: body.timezone });
      } catch {
        setTab('Basics');
        form.setError('timezone', { message: 'Choose a valid timezone.' });

        return;
      }

      if (!body.channel_id) {
        setTab('Basics');
        form.setError('channel_id', { message: 'Choose a channel.' });

        return;
      }

      try {
        const result = await save.mutateAsync({ id: program?.id, body });

        toast.success(
          program ? 'Coffee chat settings saved' : 'Coffee chat created',
        );

        if (!program && 'id' in result)
          navigate(`/dashboard/connect/${result.id}`);
      } catch (error) {
        applyApiErrors(error, form.setError);
      }
    },
    () => setTab('Basics'),
  );

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
      <Card>
        <CardHeader>
          <CardTitle>
            {program ? 'Coffee chat settings' : 'Set up your coffee chat'}
          </CardTitle>
          <CardDescription>
            Introduce people regularly and give them an easy way to get to know
            each other.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea orientation="horizontal" className="shrink-0">
            <div
              role="tablist"
              aria-label="Coffee chat settings"
              className="mb-6 flex w-max min-w-full gap-1 border-b pb-3"
            >
              {tabs.map((name, index) => (
                <Button
                  key={name}
                  id={`${id}-${name}`}
                  role="tab"
                  aria-selected={tab === name}
                  aria-controls={`${id}-panel-${name}`}
                  tabIndex={tab === name ? 0 : -1}
                  variant={tab === name ? 'secondary' : 'ghost'}
                  size="sm"
                  onClick={() => setTab(name)}
                  onKeyDown={(event) => {
                    if (
                      event.key === 'ArrowRight' ||
                      event.key === 'ArrowLeft'
                    ) {
                      event.preventDefault();

                      const next =
                        tabs[
                          (index +
                            (event.key === 'ArrowRight'
                              ? 1
                              : tabs.length - 1)) %
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
          </ScrollArea>
          <form
            onSubmit={submit}
            onInvalidCapture={onInvalid}
            className="space-y-6"
          >
            <fieldset
              disabled={!editable || save.isPending}
              className="min-w-0 space-y-5"
            >
              <section
                role="tabpanel"
                aria-labelledby={`${id}-Basics`}
                id={`${id}-panel-Basics`}
                data-tab="Basics"
                hidden={tab !== 'Basics'}
                className="space-y-5"
              >
                <Field label="Name">
                  <Input
                    maxLength={80}
                    {...register('name', { required: 'Enter a name.' })}
                  />
                </Field>
                <Controller
                  control={form.control}
                  name="channel_id"
                  rules={{ required: 'Choose a channel.' }}
                  render={({ field, fieldState }) => (
                    <LoadingField
                      pending={resources.channels.isPending}
                      label="Loading channels…"
                      fieldLabel="Draw people from"
                    >
                      <Select
                        name={field.name}
                        value={field.value}
                        items={channelOptions}
                        disabled={!editable || save.isPending}
                        onValueChange={(value) => {
                          if (value !== null) field.onChange(value);
                        }}
                      >
                        <Field
                          label="Draw people from"
                          help="Everyone eligible in this channel can be paired. People can opt out from Slack."
                        >
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
                    </LoadingField>
                  )}
                />
                {form.formState.errors.channel_id && (
                  <p role="alert" className="text-sm text-destructive">
                    {form.formState.errors.channel_id.message}
                  </p>
                )}
                <div className="grid gap-4 sm:grid-cols-2">
                  <Controller
                    control={form.control}
                    name="interval_weeks"
                    render={({ field, fieldState }) => (
                      <Select
                        name={field.name}
                        value={field.value}
                        items={intervalOptions}
                        disabled={!editable || save.isPending}
                        onValueChange={(value) => {
                          if (value !== null) field.onChange(value);
                        }}
                      >
                        <Field label="Repeat every">
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
                          {intervalOptions.map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  />
                  <Controller
                    control={form.control}
                    name="day_of_week"
                    render={({ field, fieldState }) => (
                      <Select
                        name={field.name}
                        value={field.value}
                        items={dayOptions}
                        disabled={!editable || save.isPending}
                        onValueChange={(value) => {
                          if (value !== null) field.onChange(value);
                        }}
                      >
                        <Field label="On">
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
                          {dayOptions.map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  />
                  <Field label="At">
                    <Input
                      type="time"
                      required
                      value={programTime(values)}
                      onChange={(event) => {
                        const [hour, minute] = event.target.value
                          .split(':')
                          .map(Number);

                        if (Number.isFinite(hour) && Number.isFinite(minute)) {
                          setValue('hour', hour, { shouldDirty: true });
                          setValue('minute', minute, { shouldDirty: true });
                        }
                      }}
                    />
                  </Field>
                  <Controller
                    control={form.control}
                    name="timezone"
                    rules={{ required: 'Choose a timezone.' }}
                    render={({ field, fieldState }) => (
                      <Field label="Timezone">
                        <TimezoneSelect
                          name={field.name}
                          value={field.value}
                          onValueChange={field.onChange}
                          ref={field.ref}
                          onBlur={field.onBlur}
                          aria-invalid={fieldState.invalid}
                          disabled={!editable || save.isPending}
                        />
                      </Field>
                    )}
                  />
                </div>
                {form.formState.errors.timezone && (
                  <p role="alert" className="text-sm text-destructive">
                    {form.formState.errors.timezone.message}
                  </p>
                )}
                <Field
                  label="Next round date"
                  help="Leave blank to let the regular cadence decide."
                >
                  <Input
                    type="date"
                    {...register('next_round_date', {
                      setValueAs: (value) => value || null,
                    })}
                  />
                </Field>
              </section>
              <section
                role="tabpanel"
                aria-labelledby={`${id}-Matching`}
                id={`${id}-panel-Matching`}
                data-tab="Matching"
                hidden={tab !== 'Matching'}
                className="space-y-5"
              >
                <Controller
                  control={form.control}
                  name="group_size"
                  render={({ field, fieldState }) => (
                    <Select
                      name={field.name}
                      value={field.value}
                      items={groupSizeOptions}
                      disabled={!editable || save.isPending}
                      onValueChange={(value) => {
                        if (value !== null) field.onChange(value);
                      }}
                    >
                      <Field
                        label="People in each group"
                        help="Pairs are easiest to schedule. Larger groups take the pressure off any one person."
                      >
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
                        {groupSizeOptions.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
                <label className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="mt-1"
                    {...register('strict_group_size')}
                  />
                  <span>
                    Keep groups exactly this size, even if that leaves someone
                    out
                  </span>
                </label>
                <label className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="mt-1"
                    {...register('match_working_hours')}
                  />
                  <span>Only match people whose working hours overlap</span>
                </label>
                <p className="text-xs text-muted-foreground">
                  Working hours use the timezone in each person’s Slack profile.
                </p>
              </section>
              <section
                role="tabpanel"
                aria-labelledby={`${id}-Message`}
                id={`${id}-panel-Message`}
                data-tab="Message"
                hidden={tab !== 'Message'}
                className="space-y-5"
              >
                <Controller
                  control={form.control}
                  name="intro_tone"
                  render={({ field, fieldState }) => (
                    <Select
                      name={field.name}
                      value={field.value}
                      items={introToneOptions}
                      disabled={!editable || save.isPending}
                      onValueChange={(value) => {
                        if (value !== null) field.onChange(value);
                      }}
                    >
                      <Field label="How your team works">
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
                        {introToneOptions.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" {...register('use_icebreaker')} />
                  Open each introduction with an icebreaker
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" {...register('post_stats')} />
                  Post round results in the channel
                </label>
                <p className="text-xs text-muted-foreground">
                  A short check-in asks whether each group met. The summary
                  helps the team see how introductions are working.
                </p>
              </section>
              <section
                role="tabpanel"
                aria-labelledby={`${id}-Meeting`}
                id={`${id}-panel-Meeting`}
                data-tab="Meeting"
                hidden={tab !== 'Meeting'}
                className="space-y-5"
              >
                <Controller
                  control={form.control}
                  name="meeting_minutes"
                  render={({ field, fieldState }) => (
                    <Select
                      name={field.name}
                      value={field.value}
                      items={meetingLengthOptions}
                      disabled={!editable || save.isPending}
                      onValueChange={(value) => {
                        if (value !== null) field.onChange(value);
                      }}
                    >
                      <Field label="Meeting length">
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
                        {meetingLengthOptions.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" {...register('suggest_times')} />
                  Suggest times during everyone’s working day
                </label>
                <p className="text-xs text-muted-foreground">
                  Suggested times are proposals; Morgenruf does not read
                  calendars.
                </p>
                <Controller
                  control={form.control}
                  name="video_mode"
                  render={({ field, fieldState }) => (
                    <Select
                      name={field.name}
                      value={field.value}
                      items={videoModeOptions}
                      disabled={!editable || save.isPending}
                      onValueChange={(value) => {
                        if (value !== null) field.onChange(value);
                      }}
                    >
                      <Field label="How they meet">
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
                        {videoModeOptions.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
                {values.video_mode === 'link' && (
                  <Field
                    label="Shared meeting link"
                    help="A Google Meet, Teams, or Zoom URL."
                  >
                    <Input
                      type="url"
                      placeholder="https://meet.google.com/…"
                      {...register('meeting_link')}
                    />
                  </Field>
                )}
                {values.video_mode === 'zoom' && (
                  <div className="rounded-lg border p-4 text-sm">
                    <LoadingTransition pending={resources.zoom.isPending}>
                      {resources.zoom.isPending ? (
                        <SkeletonRegion label="Checking Zoom configuration…">
                          <SkeletonText lines={2} />
                        </SkeletonRegion>
                      ) : resources.zoom.error ? (
                        <ErrorState
                          error={resources.zoom.error}
                          retry={() => resources.zoom.refetch()}
                        />
                      ) : resources.zoom.data?.configured ? (
                        <>
                          <p>
                            {resources.zoom.data.linked} people have linked
                            Zoom.
                          </p>
                          {resources.zoom.data.needs_reconnect > 0 && (
                            <p className="mt-1 text-amber-600">
                              {resources.zoom.data.needs_reconnect} need to
                              reconnect.
                            </p>
                          )}
                          <p className="mt-2 text-xs text-muted-foreground">
                            People connect their accounts from the Morgenruf tab
                            in Slack.
                          </p>
                        </>
                      ) : (
                        <p className="text-muted-foreground">
                          Zoom is not configured on this deployment. Ask the
                          operator to configure Zoom OAuth before choosing this
                          option.
                        </p>
                      )}
                    </LoadingTransition>
                  </div>
                )}
              </section>
            </fieldset>
            {program && tab === 'Members' && (
              <section
                role="tabpanel"
                aria-labelledby={`${id}-Members`}
                id={`${id}-panel-Members`}
                data-tab="Members"
              >
                <ProgramMembers programId={program.id} />
              </section>
            )}
            {Object.entries(form.formState.errors)
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
            {form.formState.errors.root && (
              <p
                role="alert"
                className="rounded-md bg-destructive/10 p-3 text-sm text-destructive"
              >
                {form.formState.errors.root.message ??
                  form.formState.errors.root.server?.message}
              </p>
            )}
            {editable && tab !== 'Members' && (
              <div className="flex justify-end gap-2 border-t pt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => navigate('/dashboard/connect')}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={save.isPending}>
                  {save.isPending
                    ? 'Saving…'
                    : program
                      ? 'Save changes'
                      : 'Create coffee chat'}
                </Button>
              </div>
            )}
            {!editable && (
              <p className="text-xs text-muted-foreground">
                A coffee chat administrator can change these settings.
              </p>
            )}
          </form>
        </CardContent>
      </Card>
      <MessagePreview values={values} />
    </div>
  );
}
