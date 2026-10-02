import {
  Children,
  cloneElement,
  isValidElement,
  useId,
  useState,
  type ReactNode,
} from 'react';
import { CalendarPlus, Mail, Trash } from 'lucide-react';
import { Controller, useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { errorMessage } from '@/common/api/errors';
import { useMemberDirectory } from '@/common/api/use-member-directory';
import { AskForDatesDialog } from '@/common/components/ask-for-dates-dialog';
import { LoadingField } from '@/common/components/loading-skeleton';
import { LoadingTransition } from '@/common/components/loading-transition';
import { EmptyState, ErrorState, PageHeader } from '@/common/components/page';
import { Person } from '@/common/components/person';
import { TimezoneSelect } from '@/common/components/timezone-select';
import { Button } from '@/common/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';
import { Input } from '@/common/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/common/components/ui/select';
import { applyApiErrors } from '@/common/forms/api-errors';
import { formatDate } from '@/common/lib/format';

import { ImportHolidaysDialog } from '../dialogs';
import {
  useCelebrations,
  useCelebrationsModule,
  type CelebrationSettingsInput,
} from '../hooks';
import {
  CelebrationSettingsSkeleton,
  HolidaysSkeleton,
  UpcomingSkeleton,
} from '../loading';

const weekdays = [
  { value: 'mon', label: 'Monday' },
  { value: 'tue', label: 'Tuesday' },
  { value: 'wed', label: 'Wednesday' },
  { value: 'thu', label: 'Thursday' },
  { value: 'fri', label: 'Friday' },
  { value: 'sat', label: 'Saturday' },
  { value: 'sun', label: 'Sunday' },
];

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

// The response lists working days as plain strings; the form keeps them that
// way and the request narrows them back to weekday keys.
type SettingsForm = Omit<CelebrationSettingsInput, 'working_days'> & {
  working_days: string[];
};

const defaults: SettingsForm = {
  channel_id: '',
  timezone: '',
  post_time: '09:00',
  birthdays: true,
  anniversaries: true,
  banners: true,
  working_days: ['mon', 'tue', 'wed', 'thu', 'fri'],
};

function StatusCard() {
  const { feature, modules } = useCelebrationsModule();
  const { settings, enable, isAdmin, canEdit } = useCelebrations();

  if (modules.isPending) return null;

  // Without the module list the page cannot say whether Celebrations is on;
  // say so rather than show nothing.
  if (modules.isError)
    return (
      <ErrorState error={modules.error} retry={() => void modules.refetch()} />
    );

  if (!feature) return null;

  if (feature.active)
    return settings.data && !settings.data.can_react ? (
      <p className="text-sm text-muted-foreground">
        Posts go out without the 🎉 reaction until Slack is re-authorised with
        the reactions permission. Nothing else changes.{' '}
        {isAdmin && (
          <a href="/install" className="font-medium text-primary underline">
            Re-authorise Slack
          </a>
        )}
      </p>
    ) : null;

  const ready = !!settings.data?.ready;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Celebrations are switched off</CardTitle>
        <CardDescription>
          {isAdmin
            ? 'Once on, Morgenruf posts birthdays and work anniversaries in your channel, and sends one message to each person with no dates on file asking for them.'
            : canEdit
              ? 'Set everything up below, then ask a workspace admin to turn Celebrations on.'
              : 'A workspace admin can turn Celebrations on.'}
        </CardDescription>
      </CardHeader>
      {isAdmin && (
        <CardContent className="flex flex-wrap items-center gap-3">
          <Button
            disabled={!ready || enable.isPending}
            onClick={() =>
              enable.mutate(undefined, {
                onSuccess: () => toast.success('Celebrations are on'),
              })
            }
          >
            {enable.isPending ? 'Turning on…' : 'Turn on celebrations'}
          </Button>
          {!ready && (
            <p className="text-sm text-muted-foreground">
              Choose a channel and a timezone below first.
            </p>
          )}
        </CardContent>
      )}
    </Card>
  );
}

function SettingsCard() {
  const { settings, channels, save, canEdit } = useCelebrations();
  const id = useId();

  const form = useForm<SettingsForm>({
    resetOptions: { keepDirtyValues: true },
    values: settings.data
      ? {
          channel_id: settings.data.channel_id ?? '',
          timezone: settings.data.timezone ?? '',
          post_time: settings.data.post_time,
          birthdays: settings.data.birthdays,
          anniversaries: settings.data.anniversaries,
          banners: settings.data.banners,
          working_days: settings.data.working_days,
        }
      : defaults,
  });

  const channelOptions = [
    { value: '', label: 'Choose a channel…' },
    ...(channels.data ?? []).map((channel) => ({
      value: channel.id,
      label: `#${channel.name}`,
    })),
  ];

  const submit = form.handleSubmit((data) =>
    save.mutate(data as CelebrationSettingsInput, {
      onSuccess: () => toast.success('Celebration settings saved'),
      onError: (error) => applyApiErrors(error, form.setError),
    }),
  );

  const errors = form.formState.errors;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Where and when</CardTitle>
        <CardDescription>
          Celebrations post once a day on working days. Birthdays and
          anniversaries that fall on a weekend or a holiday are posted on the
          last working day before.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {settings.isError ? (
          <ErrorState
            error={settings.error}
            retry={() => void settings.refetch()}
          />
        ) : (
          <LoadingTransition pending={settings.isPending}>
            {settings.isPending ? (
              <CelebrationSettingsSkeleton />
            ) : (
              <form className="space-y-5" onSubmit={submit}>
                <fieldset
                  disabled={!canEdit || save.isPending}
                  className="min-w-0 space-y-5"
                >
                  <div className="grid max-w-2xl gap-4 sm:grid-cols-2">
                    <Controller
                      control={form.control}
                      name="channel_id"
                      rules={{ required: 'Choose a channel.' }}
                      render={({ field, fieldState }) => (
                        <LoadingField
                          pending={channels.isPending}
                          label="Loading channels…"
                          fieldLabel="Channel"
                        >
                          <Select
                            name={field.name}
                            value={field.value}
                            items={channelOptions}
                            disabled={!canEdit || save.isPending}
                            onValueChange={(value) => {
                              if (value !== null) field.onChange(value);
                            }}
                          >
                            <Field
                              label="Channel"
                              help="Invite @Morgenruf to this channel so it can post there."
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
                    <Controller
                      control={form.control}
                      name="timezone"
                      rules={{ required: 'Choose a timezone.' }}
                      render={({ field, fieldState }) => (
                        <Field
                          label="Timezone"
                          help="The clock your company celebrates on. Separate from standup timezones."
                        >
                          <TimezoneSelect
                            name={field.name}
                            value={field.value || undefined}
                            onValueChange={field.onChange}
                            ref={field.ref}
                            onBlur={field.onBlur}
                            aria-invalid={fieldState.invalid}
                            disabled={!canEdit || save.isPending}
                          />
                        </Field>
                      )}
                    />
                    <div className="flex flex-col gap-2 text-sm font-medium">
                      <label htmlFor={`${id}-time`}>Post at</label>
                      <Input
                        id={`${id}-time`}
                        type="time"
                        required
                        {...form.register('post_time', { required: true })}
                      />
                    </div>
                  </div>

                  <Controller
                    control={form.control}
                    name="working_days"
                    rules={{
                      validate: (value) =>
                        value.length > 0 || 'Pick at least one working day.',
                    }}
                    render={({ field }) => (
                      <fieldset className="space-y-2">
                        <legend className="text-sm font-medium">
                          Working days
                        </legend>
                        <div className="flex flex-wrap gap-x-4 gap-y-2">
                          {weekdays.map((day) => (
                            <label
                              key={day.value}
                              className="flex items-center gap-2 text-sm"
                            >
                              <input
                                type="checkbox"
                                checked={field.value.includes(day.value)}
                                onChange={(event) =>
                                  field.onChange(
                                    event.target.checked
                                      ? [...field.value, day.value]
                                      : field.value.filter(
                                          (value) => value !== day.value,
                                        ),
                                  )
                                }
                              />
                              {day.label}
                            </label>
                          ))}
                        </div>
                      </fieldset>
                    )}
                  />

                  <div className="space-y-2">
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" {...form.register('birthdays')} />
                      Celebrate birthdays
                    </label>
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        {...form.register('anniversaries')}
                      />
                      Celebrate work anniversaries
                    </label>
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" {...form.register('banners')} />
                      Add a banner image to each post
                    </label>
                  </div>
                </fieldset>

                {Object.entries(errors).map(
                  ([field, error]) =>
                    field !== 'root' &&
                    typeof error?.message === 'string' &&
                    error.message && (
                      <p
                        key={field}
                        role="alert"
                        className="text-sm text-destructive"
                      >
                        {error.message}
                      </p>
                    ),
                )}
                {errors.root?.server && (
                  <p role="alert" className="text-sm text-destructive">
                    {errors.root.server.message}
                  </p>
                )}

                <p className="text-xs text-muted-foreground">
                  People add their dates with{' '}
                  <code className="rounded bg-muted px-1.5 py-0.5 text-foreground">
                    /morgenruf profile
                  </code>{' '}
                  or on their profile page, and can opt out there. The working
                  days and holidays are shared with other features that plan
                  around your calendar.
                </p>

                {canEdit && (
                  <Button type="submit" disabled={save.isPending}>
                    {save.isPending ? 'Saving…' : 'Save settings'}
                  </Button>
                )}
              </form>
            )}
          </LoadingTransition>
        )}
      </CardContent>
    </Card>
  );
}

function HolidaysCard() {
  const { holidays, addHoliday, removeHoliday, importHolidays, canEdit } =
    useCelebrations();
  const id = useId();
  const [day, setDay] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [importing, setImporting] = useState(false);

  function add() {
    setError('');
    addHoliday.mutate(
      { date: day, name },
      {
        onSuccess: () => {
          setDay('');
          setName('');
          toast.success('Holiday added');
        },
        onError: (failure) => setError(errorMessage(failure)),
      },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Holidays</CardTitle>
        <CardDescription>
          Your company’s days off. Nothing is posted on them, and a celebration
          that falls on one is posted the working day before.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {canEdit && (
          <form
            className="grid gap-3 sm:grid-cols-[10rem_minmax(0,1fr)_auto] sm:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              add();
            }}
          >
            <div className="flex flex-col gap-2 text-sm font-medium">
              <label htmlFor={`${id}-date`}>Date</label>
              <Input
                id={`${id}-date`}
                type="date"
                required
                value={day}
                onChange={(event) => setDay(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2 text-sm font-medium">
              <label htmlFor={`${id}-name`}>Name</label>
              <Input
                id={`${id}-name`}
                required
                maxLength={80}
                placeholder="e.g. Christmas Day"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </div>
            <Button
              type="submit"
              disabled={!day || !name.trim() || addHoliday.isPending}
            >
              {addHoliday.isPending ? 'Adding…' : 'Add holiday'}
            </Button>
          </form>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <LoadingTransition pending={holidays.isPending}>
          {holidays.isPending ? (
            <HolidaysSkeleton />
          ) : holidays.isError ? (
            <ErrorState
              error={holidays.error}
              retry={() => void holidays.refetch()}
            />
          ) : !holidays.data?.length ? (
            <EmptyState
              title="No holidays yet"
              description="Add your company’s days off, or import a list."
            />
          ) : (
            <ul aria-label="Holidays" className="divide-y">
              {holidays.data.map((holiday) => (
                <li
                  key={holiday.date}
                  className="flex items-center gap-3 py-2 text-sm"
                >
                  <span className="w-28 shrink-0 text-muted-foreground">
                    {formatDate(holiday.date)}
                  </span>
                  <span className="min-w-0 flex-1 truncate">
                    {holiday.name}
                  </span>
                  {canEdit && (
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      aria-label={`Remove ${holiday.name}`}
                      disabled={removeHoliday.isPending}
                      onClick={() =>
                        // Deleting one holiday is easy to reverse, so it
                        // offers an undo rather than asking first.
                        removeHoliday.mutate(holiday.date, {
                          onSuccess: () =>
                            toast.success(`${holiday.name} removed`, {
                              action: {
                                label: 'Undo',
                                onClick: () =>
                                  addHoliday.mutate(
                                    { date: holiday.date, name: holiday.name },
                                    {
                                      onError: (failure) =>
                                        toast.error(errorMessage(failure)),
                                    },
                                  ),
                              },
                            }),
                        })
                      }
                    >
                      <Trash />
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </LoadingTransition>

        {canEdit && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setImporting(true)}
          >
            <CalendarPlus /> Import holidays
          </Button>
        )}
      </CardContent>
      <ImportHolidaysDialog
        open={importing}
        onOpenChange={setImporting}
        run={(input) => importHolidays.mutateAsync(input)}
        pending={importHolidays.isPending}
      />
    </Card>
  );
}

function UpcomingCard() {
  const { upcoming } = useCelebrations();
  const directory = useMemberDirectory();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Coming up</CardTitle>
        <CardDescription>
          The next 30 days, and when each is posted.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <LoadingTransition pending={upcoming.isPending}>
          {upcoming.isPending ? (
            <UpcomingSkeleton />
          ) : upcoming.isError ? (
            <ErrorState
              error={upcoming.error}
              retry={() => void upcoming.refetch()}
            />
          ) : !upcoming.data?.length ? (
            <EmptyState
              title="Nothing in the next 30 days"
              description="Birthdays and anniversaries appear here once people add their dates."
            />
          ) : (
            <ul aria-label="Upcoming celebrations" className="divide-y">
              {upcoming.data.map((item) => (
                <li
                  key={`${item.kind}-${item.date}-${item.user_id}`}
                  className="flex flex-wrap items-center gap-3 py-3 text-sm"
                >
                  <Person
                    className="min-w-40 flex-1"
                    {...directory.person(item.user_id)}
                    detail={
                      item.kind === 'birthday'
                        ? '🎂 Birthday'
                        : item.years === 1
                          ? '🎉 First work anniversary'
                          : `🎉 ${item.years}-year work anniversary`
                    }
                  />
                  <span className="text-right text-muted-foreground">
                    {formatDate(item.date, {
                      weekday: 'short',
                      day: 'numeric',
                      month: 'short',
                    })}
                    {item.posted_on !== item.date && (
                      <span className="block text-xs">
                        posted{' '}
                        {formatDate(item.posted_on, {
                          weekday: 'short',
                          day: 'numeric',
                          month: 'short',
                        })}
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </LoadingTransition>
      </CardContent>
    </Card>
  );
}

export default function CelebrationsPage() {
  const { canEdit } = useCelebrations();
  const { active } = useCelebrationsModule();
  const [asking, setAsking] = useState(false);

  return (
    <div className="page">
      <PageHeader
        title="Celebrations"
        reserveActionSpace
        description="Birthdays and work anniversaries, celebrated in Slack."
        actions={
          canEdit &&
          active && (
            <Button variant="outline" onClick={() => setAsking(true)}>
              <Mail /> Ask for dates
            </Button>
          )
        }
      />

      <StatusCard />
      <SettingsCard />

      <div className="grid gap-5 md:grid-cols-2">
        <HolidaysCard />
        {canEdit && <UpcomingCard />}
      </div>

      <AskForDatesDialog open={asking} onOpenChange={setAsking} />
    </div>
  );
}
