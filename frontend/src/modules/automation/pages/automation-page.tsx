import { useState } from 'react';
import { Plus, Trash2, Zap } from 'lucide-react';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { toast } from 'sonner';

import { LoadingField } from '@/common/components/loading-skeleton';
import { LoadingTransition } from '@/common/components/loading-transition';
import { EmptyState, ErrorState, PageHeader } from '@/common/components/page';
import { Button } from '@/common/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/common/components/ui/dialog';
import { Input } from '@/common/components/ui/input';
import { Label } from '@/common/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/common/components/ui/select';
import { Textarea } from '@/common/components/ui/textarea';
import { applyApiErrors } from '@/common/forms/api-errors';

import { useAutomation, type RuleInput } from '../hooks';
import { AutomationSkeleton } from '../loading';

const triggers: Record<string, string> = {
  blocker_detected: 'a blocker is reported',
  low_participation: 'participation drops',
  standup_complete: 'a standup completes',
};

const actions: Record<string, string> = {
  post_to_channel: 'post to',
  send_dm: 'send a DM to',
  fire_webhook: 'call',
};

const triggerOptions = [
  { value: 'blocker_detected', label: 'Blocker detected' },
  { value: 'low_participation', label: 'Low participation' },
  { value: 'standup_complete', label: 'Standup complete' },
];
const actionOptions = [
  { value: 'post_to_channel', label: 'Post to channel' },
  { value: 'send_dm', label: 'Send direct message' },
  { value: 'fire_webhook', label: 'Call webhook' },
];

const templates: {
  title: string;
  description: string;
  data: Partial<RuleInput>;
}[] = [
  {
    title: 'Tell the channel about blockers',
    description: 'Post blockers where the team can help.',
    data: {
      name: 'Alert on blockers',
      trigger: 'blocker_detected',
      action: 'post_to_channel',
      action_message: ':rotating_light: {team} has blockers today:\n{blockers}',
    },
  },
  {
    title: 'Notice a quiet standup',
    description: 'Speak up when fewer people answer.',
    data: {
      name: 'Low participation warning',
      trigger: 'low_participation',
      action: 'post_to_channel',
      action_message: 'Only {participation} answered standup in {team} today.',
    },
  },
  {
    title: 'Send it somewhere else',
    description: 'Notify your own system when a standup finishes.',
    data: {
      name: 'Standup complete webhook',
      trigger: 'standup_complete',
      action: 'fire_webhook',
      action_message: '',
    },
  },
];

export default function AutomationPage() {
  const { rules, channels, create, remove, canEdit } = useAutomation();

  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);

  const form = useForm<RuleInput>({
    defaultValues: {
      name: '',
      trigger: 'blocker_detected',
      action: 'post_to_channel',
      action_target: '',
      action_message: '',
      condition_value: '50',
    },
  });
  const values = useWatch({ control: form.control });

  const channelOptions = [
    { value: '', label: 'Choose a channel' },
    ...(channels.data ?? []).map((channel) => ({
      value: channel.id,
      label: `#${channel.name}`,
    })),
  ];

  function start(data?: Partial<RuleInput>) {
    form.reset({
      name: '',
      trigger: 'blocker_detected',
      action: 'post_to_channel',
      action_target: '',
      action_message: '',
      condition_value: '50',
      ...data,
    });

    setOpen(true);
  }

  return (
    <div className="page">
      <PageHeader
        title="Automation"
        description="When something happens in a standup, do something useful about it."
        actions={
          canEdit && (
            <Button onClick={() => start()}>
              <Plus /> New rule
            </Button>
          )
        }
      />
      <LoadingTransition pending={rules.isPending}>
        {rules.isPending ? (
          <AutomationSkeleton />
        ) : rules.isError ? (
          <ErrorState error={rules.error} retry={() => void rules.refetch()} />
        ) : !rules.data?.length ? (
          <EmptyState
            title="Nothing runs by itself yet"
            description="Start from a template or build your own rule."
          />
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {rules.data.map((rule) => (
              <Card key={rule.id}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Zap className="size-4 text-primary" />
                    {rule.name}
                  </CardTitle>
                  <CardDescription>
                    When {triggers[rule.trigger] ?? rule.trigger}
                    {rule.trigger === 'low_participation' &&
                    rule.condition_value != null
                      ? ` below ${rule.condition_value}%`
                      : ''}
                    , {actions[rule.action] ?? rule.action}{' '}
                    {rule.action === 'post_to_channel'
                      ? `#${channels.data?.find((channel) => channel.id === rule.action_target)?.name ?? rule.action_target}`
                      : rule.action_target}
                    .
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {rule.action_message && (
                    <p className="whitespace-pre-wrap rounded-md bg-muted p-3 text-sm">
                      {rule.action_message}
                    </p>
                  )}
                  {canEdit && (
                    <Button
                      variant="destructive"
                      disabled={remove.isPending}
                      onClick={() => setDeleting(rule.id)}
                    >
                      <Trash2 /> Delete
                    </Button>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </LoadingTransition>
      {canEdit && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Start with a template</h2>
          <div className="grid gap-3 md:grid-cols-3">
            {templates.map((template) => (
              <button
                key={template.title}
                className="rounded-lg border bg-card p-4 text-left transition-colors hover:border-primary focus-visible:outline-2 focus-visible:outline-ring"
                onClick={() => start(template.data)}
              >
                <h3 className="text-sm font-medium">{template.title}</h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  {template.description}
                </p>
              </button>
            ))}
          </div>
        </section>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>New automation rule</DialogTitle>
            <DialogDescription>
              Choose what to watch and what should happen next.
            </DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={form.handleSubmit((data) =>
              create.mutate(
                {
                  ...data,
                  name: data.name.trim(),
                  action_target: data.action_target.trim(),
                  action_message: data.action_message?.trim() || null,
                  condition_value:
                    data.trigger === 'low_participation'
                      ? data.condition_value || '50'
                      : null,
                },
                {
                  onSuccess: () => {
                    setOpen(false);
                    toast.success('Rule created');
                  },
                  onError: (error) => applyApiErrors(error, form.setError),
                },
              ),
            )}
          >
            <div className="space-y-2">
              <Label htmlFor="rule-name">Rule name</Label>
              <Input
                id="rule-name"
                required
                {...form.register('name', { required: true })}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="rule-trigger">Trigger</Label>
                <Controller
                  control={form.control}
                  name="trigger"
                  render={({ field, fieldState }) => (
                    <Select
                      name={field.name}
                      value={field.value}
                      items={triggerOptions}
                      disabled={!canEdit || create.isPending}
                      onValueChange={(value) => {
                        if (value !== null) {
                          field.onChange(value);
                        }
                      }}
                    >
                      <SelectTrigger
                        id="rule-trigger"
                        className="w-full"
                        ref={field.ref}
                        onBlur={field.onBlur}
                        aria-invalid={fieldState.invalid}
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {triggerOptions.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
              </div>
              {values.trigger === 'low_participation' && (
                <div className="space-y-2">
                  <Label htmlFor="rule-threshold">
                    Participation threshold (%)
                  </Label>
                  <Input
                    id="rule-threshold"
                    type="number"
                    min="0"
                    max="100"
                    required
                    {...form.register('condition_value', {
                      min: {
                        value: 0,
                        message: 'Use a threshold from 0 to 100.',
                      },
                      max: {
                        value: 100,
                        message: 'Use a threshold from 0 to 100.',
                      },
                    })}
                  />
                </div>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="rule-action">Action</Label>
              <Controller
                control={form.control}
                name="action"
                render={({ field, fieldState }) => (
                  <Select
                    name={field.name}
                    value={field.value}
                    items={actionOptions}
                    disabled={!canEdit || create.isPending}
                    onValueChange={(value) => {
                      if (value !== null) {
                        field.onChange(value);
                        form.setValue('action_target', '');
                      }
                    }}
                  >
                    <SelectTrigger
                      id="rule-action"
                      className="w-full"
                      ref={field.ref}
                      onBlur={field.onBlur}
                      aria-invalid={fieldState.invalid}
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {actionOptions.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="rule-target">
                {values.action === 'fire_webhook'
                  ? 'Webhook URL'
                  : values.action === 'send_dm'
                    ? 'Slack user ID'
                    : 'Slack channel'}
              </Label>
              {values.action === 'post_to_channel' ? (
                <Controller
                  control={form.control}
                  name="action_target"
                  rules={{ required: 'Choose a channel.' }}
                  render={({ field, fieldState }) => (
                    <LoadingField
                      pending={channels.isPending}
                      label="Loading channels…"
                    >
                      <Select
                        name={field.name}
                        value={field.value}
                        items={channelOptions}
                        required
                        disabled={!canEdit || create.isPending}
                        onValueChange={(value) => {
                          if (value !== null) {
                            field.onChange(value);
                          }
                        }}
                      >
                        <SelectTrigger
                          id="rule-target"
                          className="w-full"
                          ref={field.ref}
                          onBlur={field.onBlur}
                          aria-invalid={fieldState.invalid}
                        >
                          <SelectValue />
                        </SelectTrigger>
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
              ) : (
                <Input
                  id="rule-target"
                  type={values.action === 'fire_webhook' ? 'url' : 'text'}
                  required
                  {...form.register('action_target', { required: true })}
                />
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="rule-message">Message template</Label>
              <Textarea
                id="rule-message"
                rows={4}
                {...form.register('action_message')}
              />
              <p className="text-xs text-muted-foreground">
                {
                  'Supports {team}, {trigger}, {blockers}, and {participation}. Leave blank for the default message.'
                }
              </p>
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
                    {field.replaceAll('_', ' ')}: {error.message}
                  </p>
                ),
            )}
            {form.formState.errors.root?.server && (
              <p role="alert" className="text-sm text-destructive">
                {form.formState.errors.root.server.message}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? 'Saving…' : 'Save rule'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog
        open={deleting !== null}
        onOpenChange={(next) => {
          if (!next) setDeleting(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this rule?</DialogTitle>
            <DialogDescription>
              This automation will stop running.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => {
                if (deleting !== null)
                  remove.mutate(deleting, {
                    onSuccess: () => {
                      setDeleting(null);
                      toast.success('Rule deleted');
                    },
                  });
              }}
            >
              Delete rule
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
