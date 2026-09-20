import {
  Children,
  cloneElement,
  isValidElement,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { Plus, Search, X } from 'lucide-react';
import {
  Controller,
  FormProvider,
  useForm,
  useFormContext,
  useWatch,
  type FieldPath,
} from 'react-hook-form';
import { toast } from 'sonner';

import {
  LoadingField,
  SkeletonPeople,
  SkeletonRegion,
} from '@/common/components/loading-skeleton';
import { LoadingTransition } from '@/common/components/loading-transition';
import { ErrorState } from '@/common/components/page';
import { Person } from '@/common/components/person';
import { TimezoneSelect } from '@/common/components/timezone-select';
import { Button } from '@/common/components/ui/button';
import { Checkbox } from '@/common/components/ui/checkbox';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/common/components/ui/dialog';
import { Input } from '@/common/components/ui/input';
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/common/components/ui/input-group';
import { ScrollArea } from '@/common/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/common/components/ui/select';
import { Textarea } from '@/common/components/ui/textarea';
import { applyApiErrors } from '@/common/forms/api-errors';
import { useTabbedFormValidation } from '@/common/forms/use-tabbed-form-validation';

import {
  standupDefaults,
  validTimezone,
  weekdays,
  workspaceSettingFields,
} from './form-utils';
import {
  useStandupMutations,
  useStandupResources,
  type Standup,
  type StandupInput,
} from './hooks';

function Field({
  label,
  children,
  help,
  name,
}: {
  label: string;
  children: ReactNode;
  help?: string;
  name?: FieldPath<StandupInput>;
}) {
  const id = useId();
  const form = useFormContext<StandupInput>();
  const first = Children.toArray(children)[0];
  const fieldName =
    name ??
    (isValidElement<{ name?: FieldPath<StandupInput> }>(first)
      ? first.props.name
      : undefined);
  const error = fieldName
    ? form.getFieldState(fieldName, form.formState).error?.message
    : undefined;
  const describedBy =
    [help && `${id}-help`, error && `${id}-error`].filter(Boolean).join(' ') ||
    undefined;
  return (
    <div className="flex min-w-0 flex-col gap-2 text-sm font-medium">
      <label htmlFor={id}>{label}</label>
      {Children.map(children, (child, index) =>
        index === 0 &&
        isValidElement<{
          id?: string;
          'aria-describedby'?: string;
          'aria-invalid'?: boolean;
        }>(child)
          ? cloneElement(child, {
              id,
              'aria-describedby':
                [describedBy, child.props['aria-describedby']]
                  .filter(Boolean)
                  .join(' ') || undefined,
              'aria-invalid': !!error || child.props['aria-invalid'],
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
      {error && (
        <p
          id={`${id}-error`}
          role="alert"
          className="text-sm font-normal text-destructive"
        >
          {error}
        </p>
      )}
    </div>
  );
}

function ToggleField({
  name,
  label,
  help,
}: {
  name:
    | 'digest_enabled'
    | 'nudge_missing'
    | 'post_to_thread'
    | 'post_summary'
    | 'notify_on_report'
    | 'ai_summary_enabled';
  label: string;
  help?: string;
}) {
  const { control } = useFormContext<StandupInput>();
  const id = useId();
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <div>
          <label
            className="flex cursor-pointer items-start gap-3 text-sm"
            htmlFor={id}
          >
            <Checkbox
              id={id}
              name={field.name}
              ref={field.ref}
              checked={!!field.value}
              onCheckedChange={field.onChange}
              onBlur={field.onBlur}
              className="mt-0.5 after:inset-0"
              aria-invalid={fieldState.invalid}
              aria-describedby={
                fieldState.error
                  ? `${id}-error`
                  : help
                    ? `${id}-help`
                    : undefined
              }
            />
            <span>{label}</span>
          </label>
          {help && (
            <p
              id={`${id}-help`}
              className="mt-1 pl-7 text-xs text-muted-foreground"
            >
              {help}
            </p>
          )}
          {fieldState.error && (
            <p
              id={`${id}-error`}
              role="alert"
              className="mt-2 text-sm text-destructive"
            >
              {fieldState.error.message}
            </p>
          )}
        </div>
      )}
    />
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

const tabs = [
  'Basics',
  'Schedule',
  'Questions',
  'Delivery',
  'Workspace',
] as const;
const fieldTabs: Record<string, (typeof tabs)[number]> = {
  name: 'Basics',
  channel_id: 'Basics',
  participants: 'Basics',
  schedule_time: 'Schedule',
  schedule_tz: 'Schedule',
  schedule_days: 'Schedule',
  reminder_minutes: 'Schedule',
  questions: 'Questions',
  report_channel: 'Delivery',
  report_time: 'Delivery',
  digest_email: 'Delivery',
  digest_enabled: 'Delivery',
  nudge_missing: 'Delivery',
  nudge_minutes_before: 'Delivery',
  post_to_thread: 'Delivery',
  post_summary: 'Delivery',
  notify_on_report: 'Delivery',
  group_by: 'Delivery',
  edit_window: 'Workspace',
  jira_base_url: 'Workspace',
  github_repo: 'Workspace',
  linear_team: 'Workspace',
  ai_provider: 'Workspace',
  ai_summary_enabled: 'Workspace',
};

export function StandupEditor({
  standup,
  workspace,
  close,
}: {
  standup?: Standup;
  workspace?: Standup;
  close: () => void;
}) {
  const id = useId();
  const [tab, setTab] = useState<(typeof tabs)[number]>('Basics');
  const [templateGallery, setTemplateGallery] = useState(false);
  const [memberSearch, setMemberSearch] = useState('');
  const memberSearchInput = useRef<HTMLInputElement>(null);

  const form = useForm<StandupInput>({
    defaultValues: standupDefaults(standup, workspace),
    shouldFocusError: false,
  });
  const [focusTarget, setFocusTarget] = useState<{ field: string } | null>(
    null,
  );
  const daysButton = useRef<HTMLButtonElement>(null);
  const addQuestion = useRef<HTMLButtonElement>(null);
  const revealError = (field: string) => {
    const tabName = fieldTabs[field.split('.')[0]];
    if (tabName) setTab(tabName);
    setFocusTarget({ field });
  };
  useLayoutEffect(() => {
    if (!focusTarget) return;
    const field = focusTarget.field;
    if (field === 'schedule_days') daysButton.current?.focus();
    else if (field === 'participants') memberSearchInput.current?.focus();
    else if (field === 'questions' && !form.getValues('questions')?.length)
      addQuestion.current?.focus();
    else
      form.setFocus(
        (field === 'questions'
          ? 'questions.0'
          : field) as FieldPath<StandupInput>,
      );
  }, [focusTarget, form]);
  const onInvalid = useTabbedFormValidation(tabs, setTab, form.setError);
  const {
    register,
    setValue,
    handleSubmit,
    formState: { errors, dirtyFields },
  } = form;

  const values = useWatch({ control: form.control });
  const resources = useStandupResources(values.channel_id);
  const { save } = useStandupMutations();

  const participants = values.participants ?? [];
  const memberQuery = memberSearch.trim().toLowerCase();
  const members = resources.members.data ?? [];
  const matchingMembers = members.filter((member) =>
    [member.name, member.display_name, member.email, member.id]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
      .includes(memberQuery),
  );
  const questions = values.questions ?? [];
  const days = values.schedule_days ?? [];
  const setQuestions = (next: string[]) => {
    form.clearErrors('questions');
    setValue('questions', next, { shouldDirty: true });
  };

  const onSubmit = handleSubmit(
    async (body) => {
      if (!body.schedule_days?.length) {
        form.setError('schedule_days', { message: 'Choose at least one day.' });
        revealError('schedule_days');

        return;
      }

      if (!validTimezone(body.schedule_tz ?? '')) {
        form.setError('schedule_tz', { message: 'Choose a valid timezone.' });
        revealError('schedule_tz');

        return;
      }

      if (!body.questions?.some((q) => q.trim())) {
        form.setError('questions', { message: 'Add at least one question.' });
        revealError('questions');

        return;
      }

      try {
        const payload = {
          ...body,
          questions: body.questions.filter((q) => q.trim()),
        };
        // Creating a schedule must not reset shared settings, including when
        // no existing schedule is available to expose the workspace values.
        if (!standup) {
          for (const field of workspaceSettingFields) {
            if (!dirtyFields[field]) delete payload[field];
          }
        }
        await save.mutateAsync({
          id: standup?.id,
          body: payload,
        });
        toast.success(standup ? 'Standup updated' : 'Standup created');
        close();
      } catch (error) {
        const fields: string[] = [];
        applyApiErrors<StandupInput>(error, (field, issue) => {
          if (field === 'root.server' || fieldTabs[field.split('.')[0]]) {
            form.setError(field, issue);
            fields.push(field);
          } else {
            form.setError('root.server', issue);
          }
        });
        const first = fields.find((field) => fieldTabs[field.split('.')[0]]);
        if (first) revealError(first);
      }
    },
    (invalid) => {
      const first = Object.keys(invalid)[0];
      if (first) revealError(first);
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
    <FormProvider {...form}>
      <Dialog
        open
        onOpenChange={(open) => {
          if (!open && !save.isPending) close();
        }}
      >
        <DialogContent
          className="gap-5 p-5 sm:max-w-3xl sm:p-6"
          showCloseButton={!save.isPending}
        >
          <DialogHeader>
            <DialogTitle>
              {standup ? 'Edit standup' : 'New standup'}
            </DialogTitle>
            <DialogDescription>
              Choose who takes part, when they are asked, and how answers are
              shared.
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={onSubmit}
            onInvalidCapture={onInvalid}
            className="flex min-h-0 flex-col gap-4"
          >
            <ScrollArea orientation="horizontal" className="shrink-0">
              <div
                role="tablist"
                aria-label="Standup settings"
                className="flex w-max min-w-full gap-1 border-b pb-3"
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
                      if (
                        event.key === 'ArrowRight' ||
                        event.key === 'ArrowLeft' ||
                        event.key === 'Home' ||
                        event.key === 'End'
                      ) {
                        event.preventDefault();

                        const next =
                          event.key === 'Home'
                            ? tabs[0]
                            : event.key === 'End'
                              ? tabs[tabs.length - 1]
                              : tabs[
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
            <DialogBody>
              <section
                role="tabpanel"
                aria-labelledby={`${id}-Basics`}
                id={`${id}-panel-Basics`}
                data-tab="Basics"
                hidden={tab !== 'Basics'}
                className="space-y-5"
              >
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Standup name">
                    <Input
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
                        fieldLabel="Channel"
                      >
                        <Select
                          name={field.name}
                          value={field.value}
                          items={channelOptions}
                          disabled={save.isPending}
                          onValueChange={(value) => {
                            if (value !== null) field.onChange(value);
                          }}
                        >
                          <Field label="Channel" name="channel_id">
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
                </div>

                <fieldset className="space-y-3">
                  <legend className="mb-0 text-sm font-medium">
                    Participants
                  </legend>
                  {errors.participants?.message && (
                    <p
                      id={`${id}-participants-error`}
                      role="alert"
                      className="text-sm text-destructive"
                    >
                      {errors.participants.message}
                    </p>
                  )}
                  <p className="text-sm text-muted-foreground">
                    Leave everyone unselected to include the whole channel.
                  </p>
                  <InputGroup className="h-9">
                    <InputGroupAddon>
                      <Search aria-hidden="true" />
                    </InputGroupAddon>
                    <InputGroupInput
                      ref={memberSearchInput}
                      aria-describedby={
                        errors.participants?.message
                          ? `${id}-participants-error`
                          : undefined
                      }
                      placeholder="Search participants…"
                      aria-label="Search participants"
                      value={memberSearch}
                      onChange={(event) => setMemberSearch(event.target.value)}
                    />
                    {memberSearch && (
                      <InputGroupAddon align="inline-end">
                        <InputGroupButton
                          aria-label="Clear participant search"
                          size="icon-xs"
                          onClick={() => {
                            setMemberSearch('');
                            memberSearchInput.current?.focus();
                          }}
                        >
                          <X aria-hidden="true" />
                        </InputGroupButton>
                      </InputGroupAddon>
                    )}
                  </InputGroup>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={
                        resources.members.isPending ||
                        !!resources.members.error ||
                        !matchingMembers.length
                      }
                      onClick={() =>
                        setValue(
                          'participants',
                          [
                            ...new Set([
                              ...participants,
                              ...matchingMembers.map((member) => member.id),
                            ]),
                          ],
                          { shouldDirty: true },
                        )
                      }
                    >
                      {memberQuery
                        ? 'Select results'
                        : 'Select all participants'}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        setValue('participants', [], { shouldDirty: true })
                      }
                    >
                      Use whole channel
                    </Button>
                    <p
                      className="text-xs text-muted-foreground sm:ml-auto"
                      role="status"
                    >
                      {participants.length
                        ? `${participants.length} selected`
                        : 'Everyone in the channel'}
                    </p>
                  </div>
                  <LoadingTransition pending={resources.members.isPending}>
                    {resources.members.isPending ? (
                      <SkeletonRegion label="Loading participants…">
                        <SkeletonPeople />
                      </SkeletonRegion>
                    ) : resources.members.error ? (
                      <ErrorState
                        error={resources.members.error}
                        retry={() => resources.members.refetch()}
                      />
                    ) : (
                      <ScrollArea
                        className="max-h-52 rounded-lg border"
                        contentClassName="grid gap-2 p-2 sm:grid-cols-2"
                        viewportProps={{
                          role: 'region',
                          'aria-label': 'Participants',
                        }}
                      >
                        {!matchingMembers.length && (
                          <p className="px-3 py-5 text-center text-sm text-muted-foreground sm:col-span-2">
                            {members.length
                              ? 'No participants match your search.'
                              : 'No participants available.'}
                          </p>
                        )}
                        {matchingMembers.map((member) => (
                          <label
                            key={member.id}
                            className="flex min-w-0 cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/60 has-focus-visible:border-ring has-focus-visible:ring-2 has-focus-visible:ring-ring/30 has-data-checked:border-primary has-data-checked:bg-primary/5"
                          >
                            <Checkbox
                              className="after:inset-0"
                              checked={participants.includes(member.id)}
                              onCheckedChange={(checked) =>
                                setValue(
                                  'participants',
                                  checked
                                    ? [...participants, member.id]
                                    : participants.filter(
                                        (value) => value !== member.id,
                                      ),
                                  { shouldDirty: true },
                                )
                              }
                            />
                            <Person
                              {...resources.members.person(member.id)}
                              size="compact"
                            />
                          </label>
                        ))}
                      </ScrollArea>
                    )}
                  </LoadingTransition>
                </fieldset>
              </section>
              <section
                role="tabpanel"
                aria-labelledby={`${id}-Schedule`}
                id={`${id}-panel-Schedule`}
                data-tab="Schedule"
                hidden={tab !== 'Schedule'}
                className="space-y-5"
              >
                <div>
                  <h3 className="text-sm font-semibold">When to check in</h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Your team receives a prompt on these days, in this timezone.
                  </p>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Time">
                    <Input
                      type="time"
                      {...register('schedule_time', {
                        required: 'Set a time.',
                      })}
                    />
                  </Field>
                  <Controller
                    control={form.control}
                    name="schedule_tz"
                    render={({ field, fieldState }) => (
                      <Field label="Timezone">
                        <TimezoneSelect
                          name={field.name}
                          value={field.value}
                          onValueChange={field.onChange}
                          ref={field.ref}
                          onBlur={field.onBlur}
                          aria-invalid={fieldState.invalid}
                          disabled={save.isPending}
                        />
                      </Field>
                    )}
                  />
                </div>

                <fieldset>
                  <legend className="mb-2 text-sm font-medium">Days</legend>
                  <div className="flex flex-wrap gap-2">
                    {weekdays.map((day) => (
                      <Button
                        key={day}
                        ref={day === weekdays[0] ? daysButton : undefined}
                        aria-describedby={
                          errors.schedule_days ? `${id}-days-error` : undefined
                        }
                        type="button"
                        size="sm"
                        variant={days.includes(day) ? 'default' : 'outline'}
                        aria-pressed={days.includes(day)}
                        onClick={() => {
                          form.clearErrors('schedule_days');
                          setValue(
                            'schedule_days',
                            days.includes(day)
                              ? days.filter((value) => value !== day)
                              : [...days, day],
                            { shouldDirty: true },
                          );
                        }}
                      >
                        {day[0].toUpperCase() + day.slice(1)}
                      </Button>
                    ))}
                  </div>
                  {errors.schedule_days && (
                    <p
                      id={`${id}-days-error`}
                      role="alert"
                      className="mt-2 text-sm text-destructive"
                    >
                      {errors.schedule_days.message}
                    </p>
                  )}
                </fieldset>
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
                      <Field
                        label="Remind participants before standup"
                        name="reminder_minutes"
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
                aria-labelledby={`${id}-Questions`}
                id={`${id}-panel-Questions`}
                data-tab="Questions"
                hidden={tab !== 'Questions'}
                className="space-y-5"
              >
                <p className="text-sm text-muted-foreground">
                  Ask a few focused questions to help your team share progress.
                </p>
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
                    <ScrollArea
                      className="max-h-64"
                      contentClassName="grid gap-2 p-1 sm:grid-cols-2"
                      viewportProps={{
                        role: 'region',
                        'aria-label': 'Question templates',
                      }}
                    >
                      {resources.templates.isPending && (
                        <SkeletonRegion
                          label="Loading question templates…"
                          className="sm:col-span-2"
                        >
                          <SkeletonPeople rows={4} />
                        </SkeletonRegion>
                      )}
                      {resources.templates.data?.map((template) => (
                        <button
                          key={template.id}
                          type="button"
                          className="rounded-lg border p-3 text-left hover:bg-muted"
                          onClick={() => {
                            setQuestions(template.questions ?? []);
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
                      {!resources.templates.isPending &&
                        !resources.templates.error &&
                        !resources.templates.data?.length && (
                          <p className="p-3 text-sm text-muted-foreground sm:col-span-2">
                            No question templates available.
                          </p>
                        )}
                    </ScrollArea>
                  )}
                  {questions.map((_, index) => (
                    <div
                      key={index}
                      className="flex items-start gap-2 rounded-lg border bg-muted/20 p-3"
                    >
                      <div className="min-w-0 flex-1">
                        <Field label={`Question ${index + 1}`}>
                          <Textarea
                            rows={2}
                            {...register(`questions.${index}`, {
                              onChange: () => form.clearErrors('questions'),
                            })}
                            aria-invalid={!!errors.questions?.message}
                            aria-describedby={
                              errors.questions?.message
                                ? `${id}-questions-error`
                                : undefined
                            }
                          />
                        </Field>
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="mt-6"
                        aria-label={`Remove question ${index + 1}`}
                        onClick={() =>
                          setQuestions(
                            questions.filter(
                              (_, position) => position !== index,
                            ),
                          )
                        }
                      >
                        <X className="size-4" />
                      </Button>
                    </div>
                  ))}
                  {errors.questions?.message && (
                    <p
                      id={`${id}-questions-error`}
                      role="alert"
                      className="text-sm text-destructive"
                    >
                      {errors.questions.message}
                    </p>
                  )}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    ref={addQuestion}
                    onClick={() => setQuestions([...questions, ''])}
                  >
                    <Plus className="size-4" />
                    Add question
                  </Button>
                </div>
              </section>
              <section
                role="tabpanel"
                aria-labelledby={`${id}-Delivery`}
                id={`${id}-panel-Delivery`}
                data-tab="Delivery"
                hidden={tab !== 'Delivery'}
                className="space-y-6"
              >
                <div className="space-y-4">
                  <div>
                    <h3 className="text-sm font-semibold">Slack report</h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Choose where and how your team’s answers are shared.
                    </p>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Controller
                      control={form.control}
                      name="report_channel"
                      render={({ field }) => (
                        <Select
                          name={field.name}
                          value={field.value}
                          items={reportChannelOptions}
                          disabled={save.isPending}
                          onValueChange={(value) => {
                            if (value !== null) field.onChange(value);
                          }}
                        >
                          <Field label="Report channel" name="report_channel">
                            <SelectTrigger
                              className="w-full"
                              ref={field.ref}
                              onBlur={field.onBlur}
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
                        <Field label="Group report by" name="group_by">
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

                  <ToggleField
                    name="post_summary"
                    label="Post a daily summary to the channel"
                  />
                  <ToggleField
                    name="post_to_thread"
                    label="Post answers as a Slack thread"
                  />
                  <ToggleField
                    name="notify_on_report"
                    label="Mention participants when the report posts"
                  />
                </div>
                <div className="space-y-4 rounded-lg border p-4">
                  <h3 className="text-sm font-semibold">Email digest</h3>
                  <ToggleField
                    name="digest_enabled"
                    label="Send that email daily"
                    help="This standup’s answers, sent after its reporting window."
                  />
                  <Field label="Daily email to">
                    <Input
                      type="email"
                      placeholder="lead@company.com"
                      {...register('digest_email')}
                    />
                  </Field>
                </div>
                <div className="space-y-4 rounded-lg border p-4">
                  <h3 className="text-sm font-semibold">Missing responses</h3>
                  <ToggleField
                    name="nudge_missing"
                    label="Privately remind people who have not answered"
                    help="People on leave and those who have skipped today are left alone."
                  />
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
              </section>
              <section
                role="tabpanel"
                aria-labelledby={`${id}-Workspace`}
                id={`${id}-panel-Workspace`}
                data-tab="Workspace"
                hidden={tab !== 'Workspace'}
                className="space-y-5"
              >
                <div className="rounded-lg border bg-muted/30 p-4">
                  <h3 className="mb-1 font-medium">
                    Shared workspace settings
                  </h3>
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
                          <Field label="Edit window" name="edit_window">
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
                      <Input
                        placeholder="org/repo"
                        {...register('github_repo')}
                      />
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
                          <Field label="AI provider" name="ai_provider">
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
                    <ToggleField
                      name="ai_summary_enabled"
                      label="Enable AI-generated daily summary"
                    />
                  </div>
                  <p className="mt-3 text-xs text-muted-foreground">
                    An API key for the chosen AI provider must be configured on
                    the server.
                  </p>
                </div>
              </section>
              {errors.root && (
                <p
                  role="alert"
                  className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive"
                >
                  {errors.root.message ?? errors.root.server?.message}
                </p>
              )}
            </DialogBody>
            <DialogFooter className="border-t pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={close}
                disabled={save.isPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={save.isPending}>
                {save.isPending ? 'Saving…' : 'Save standup'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </FormProvider>
  );
}
