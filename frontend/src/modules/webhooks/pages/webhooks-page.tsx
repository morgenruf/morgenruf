import { useState } from 'react';
import {
  History,
  Pencil,
  Plus,
  RefreshCw,
  Send,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { useForm, useWatch } from 'react-hook-form';
import { toast } from 'sonner';

import {
  SkeletonRegion,
  SkeletonTable,
} from '@/common/components/loading-skeleton';
import { LoadingTransition } from '@/common/components/loading-transition';
import { EmptyState, ErrorState, PageHeader } from '@/common/components/page';
import { SecretPanel } from '@/common/components/secret-panel';
import { Badge } from '@/common/components/ui/badge';
import { Button } from '@/common/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';
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
import { Label } from '@/common/components/ui/label';
import { ScrollArea } from '@/common/components/ui/scroll-area';
import { applyApiErrors } from '@/common/forms/api-errors';
import { formatDate } from '@/common/lib/format';

import {
  useWebhookDeliveries,
  useWebhooks,
  useWebhookTest,
  type Webhook,
  type WebhookInput,
} from '../hooks';
import { WebhooksSkeleton } from '../loading';

const eventLabels: Record<string, string> = {
  'standup.completed': 'Standup completed',
  'blocker.detected': 'Blocker detected',
  'participation.low': 'Low participation',
};

function WebhookCard({
  hook,
  canEdit,
  busy,
  edit,
  rotate,
  remove,
}: {
  hook: Webhook;
  canEdit: boolean;
  busy: boolean;
  edit: () => void;
  rotate: () => void;
  remove: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const deliveries = useWebhookDeliveries(String(hook.id), expanded);
  const test = useWebhookTest(String(hook.id));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="break-all text-sm">{hook.url}</CardTitle>
        <CardDescription className="flex flex-wrap items-center gap-2">
          <Badge variant={hook.signed ? 'secondary' : 'outline'}>
            {hook.signed ? (
              <>
                <ShieldCheck className="size-3" /> Signed
              </>
            ) : (
              'Unsigned'
            )}
          </Badge>
          {hook.secret_prefix && <code>{hook.secret_prefix}…</code>}
          <span>Added {formatDate(hook.created_at)}</span>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          {hook.events.map((event) => (
            <Badge key={event} variant="outline">
              {eventLabels[event] ?? event}
            </Badge>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {canEdit && (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={edit}
                disabled={busy}
              >
                <Pencil /> Edit
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={test.isPending || busy}
                onClick={() => test.mutate()}
              >
                <Send />
                {test.isPending ? 'Sending…' : 'Send test event'}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={rotate}
              >
                <RefreshCw /> Rotate secret
              </Button>
            </>
          )}
          <Button
            size="sm"
            variant="outline"
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
          >
            <History />
            {expanded ? 'Hide deliveries' : 'Deliveries'}
          </Button>
          {canEdit && (
            <Button
              size="sm"
              variant="destructive"
              disabled={busy}
              onClick={remove}
            >
              <Trash2 /> Delete
            </Button>
          )}
        </div>
        {test.data && (
          <p
            role="status"
            className={
              test.data.ok
                ? 'text-sm text-emerald-700 dark:text-emerald-400'
                : 'text-sm text-destructive'
            }
          >
            {test.data.ok ? 'Test event delivered' : 'Test event failed'}
            {test.data.status_code ? ` (HTTP ${test.data.status_code})` : ''}
            {test.data.error ? `: ${test.data.error}` : ''}
          </p>
        )}
        {expanded && (
          <section aria-label="Recent deliveries" className="border-t pt-4">
            <LoadingTransition pending={deliveries.isPending}>
              {deliveries.isPending ? (
                <SkeletonRegion label="Loading recent deliveries…">
                  <SkeletonTable columns={6} />
                </SkeletonRegion>
              ) : deliveries.isError ? (
                <ErrorState
                  error={deliveries.error}
                  retry={() => void deliveries.refetch()}
                />
              ) : !deliveries.data?.length ? (
                <EmptyState title="No deliveries recorded yet" />
              ) : (
                <ScrollArea orientation="horizontal" className="min-w-0">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b text-muted-foreground">
                        <th className="p-2">Status</th>
                        <th className="p-2">Event</th>
                        <th className="p-2">When</th>
                        <th className="p-2">Duration</th>
                        <th className="p-2">Signing</th>
                        <th className="p-2">Error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {deliveries.data.map((delivery) => (
                        <tr
                          key={delivery.id}
                          className="border-b last:border-0"
                        >
                          <td
                            className={`p-2 ${delivery.ok ? 'text-emerald-700 dark:text-emerald-400' : 'text-destructive'}`}
                          >
                            {delivery.status_code ?? 'No response'}
                          </td>
                          <td className="p-2">
                            {eventLabels[delivery.event_type] ??
                              delivery.event_type}
                          </td>
                          <td className="whitespace-nowrap p-2">
                            {formatDate(delivery.created_at, {
                              month: 'short',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </td>
                          <td className="whitespace-nowrap p-2">
                            {delivery.duration_ms} ms
                          </td>
                          <td className="p-2">
                            {delivery.signed ? 'Signed' : 'Unsigned'}
                          </td>
                          <td className="p-2">{delivery.error ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </ScrollArea>
              )}
            </LoadingTransition>
          </section>
        )}
      </CardContent>
    </Card>
  );
}

export default function WebhooksPage() {
  const { webhooks, catalog, save, rotate, remove, canEdit } = useWebhooks();

  const [editor, setEditor] = useState<{ id?: string } | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<{
    kind: 'delete' | 'rotate';
    id: string;
  } | null>(null);

  const form = useForm<WebhookInput>({
    defaultValues: { url: '', events: [] },
  });
  const selected = useWatch({ control: form.control, name: 'events' }) ?? [];

  function openEditor(hook?: Webhook) {
    form.reset({
      url: hook?.url ?? '',
      events: hook?.events ?? catalog.data?.default ?? [],
    });
    setEditor({ id: hook ? String(hook.id) : undefined });
  }

  const busy = save.isPending || rotate.isPending || remove.isPending;

  return (
    <div className="page">
      <PageHeader
        title="Webhooks"
        description="Send signed standup events to your own systems."
        actions={
          canEdit && (
            <Button onClick={() => openEditor()} disabled={!catalog.data}>
              <Plus /> Add webhook
            </Button>
          )
        }
      />
      {catalog.isError && (
        <ErrorState
          error={catalog.error}
          retry={() => void catalog.refetch()}
        />
      )}
      <LoadingTransition pending={webhooks.isPending}>
        {webhooks.isPending ? (
          <WebhooksSkeleton />
        ) : webhooks.isError ? (
          <ErrorState
            error={webhooks.error}
            retry={() => void webhooks.refetch()}
          />
        ) : !webhooks.data?.length ? (
          <EmptyState
            title="No webhooks yet"
            description={
              <div className="space-y-2">
                <p>
                  Post standup activity to a build pipeline, status page, or
                  anything that accepts HTTP events.
                </p>
                <p>
                  {catalog.data?.events
                    .map((event) => eventLabels[event] ?? event)
                    .join(' · ')}
                </p>
              </div>
            }
          />
        ) : (
          <div className="space-y-4">
            {webhooks.data.map((hook) => (
              <WebhookCard
                key={hook.id}
                hook={hook}
                canEdit={canEdit}
                busy={busy}
                edit={() => openEditor(hook)}
                rotate={() =>
                  setConfirmation({ kind: 'rotate', id: String(hook.id) })
                }
                remove={() =>
                  setConfirmation({ kind: 'delete', id: String(hook.id) })
                }
              />
            ))}
          </div>
        )}
      </LoadingTransition>
      <Dialog
        open={editor !== null}
        onOpenChange={(open) => {
          if (!open) setEditor(null);
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editor?.id ? 'Edit webhook' : 'Add webhook'}
            </DialogTitle>
            <DialogDescription>
              Choose the destination and the events it should receive.
            </DialogDescription>
          </DialogHeader>
          <form
            className="flex min-h-0 flex-col gap-4"
            onSubmit={form.handleSubmit((data) => {
              if (!data.events?.length) {
                form.setError('events', {
                  message: 'Pick at least one event.',
                });

                return;
              }

              save.mutate(
                { id: editor?.id, data, receive: setSecret },
                {
                  onSuccess: () => {
                    toast.success(
                      editor?.id ? 'Webhook updated' : 'Webhook created',
                    );
                    setEditor(null);
                  },
                  onError: (error) => applyApiErrors(error, form.setError),
                },
              );
            })}
          >
            <DialogBody>
              <div className="space-y-2">
                <Label htmlFor="webhook-url">Destination URL</Label>
                <Input
                  id="webhook-url"
                  type="url"
                  placeholder="https://example.com/webhook"
                  required
                  {...form.register('url', { required: true })}
                />
              </div>
              <fieldset className="space-y-3">
                <legend className="mb-2 text-sm font-medium">Send on</legend>
                {catalog.data?.events.map((event) => (
                  <label
                    key={event}
                    className="flex items-center gap-2 text-sm"
                  >
                    <Checkbox
                      checked={selected.includes(event)}
                      onCheckedChange={(checked) =>
                        form.setValue(
                          'events',
                          checked
                            ? [...selected, event]
                            : selected.filter((item) => item !== event),
                          { shouldDirty: true },
                        )
                      }
                    />
                    {eventLabels[event] ?? event}
                  </label>
                ))}
                {form.formState.errors.events && (
                  <p role="alert" className="text-sm text-destructive">
                    {form.formState.errors.events.message}
                  </p>
                )}
              </fieldset>
              {form.formState.errors.url && (
                <p role="alert" className="text-sm text-destructive">
                  {form.formState.errors.url.message}
                </p>
              )}
              {form.formState.errors.root?.server && (
                <p role="alert" className="text-sm text-destructive">
                  {form.formState.errors.root.server.message}
                </p>
              )}
            </DialogBody>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setEditor(null)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={save.isPending}>
                {save.isPending ? 'Saving…' : 'Save webhook'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <SecretPanel
        title="Copy your signing secret"
        value={secret}
        onDismiss={() => {
          setSecret(null);
          save.reset();
          rotate.reset();
        }}
      />
      <Dialog
        open={confirmation !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmation(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {confirmation?.kind === 'rotate'
                ? 'Rotate this signing secret?'
                : 'Delete this webhook?'}
            </DialogTitle>
            <DialogDescription>
              {confirmation?.kind === 'rotate'
                ? 'Deliveries signed with the old secret will stop verifying immediately. Update your receiver with the new secret.'
                : 'Morgenruf will stop sending events to this destination.'}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmation(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => {
                if (!confirmation) return;

                const onSuccess = () => {
                  setConfirmation(null);
                  toast.success(
                    confirmation.kind === 'rotate'
                      ? 'Secret rotated'
                      : 'Webhook deleted',
                  );
                };

                if (confirmation.kind === 'rotate')
                  rotate.mutate(
                    { id: confirmation.id, receive: setSecret },
                    { onSuccess },
                  );
                else remove.mutate(confirmation.id, { onSuccess });
              }}
            >
              {confirmation?.kind === 'rotate'
                ? 'Rotate secret'
                : 'Delete webhook'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
