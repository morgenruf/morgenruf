import {
  Copy,
  ExternalLink,
  Globe,
  Mail,
  Puzzle,
  Settings2,
} from 'lucide-react';
import { useForm } from 'react-hook-form';
import { Link } from 'react-router';
import { toast } from 'sonner';

import { api } from '@/common/api/client';
import { errorMessage } from '@/common/api/errors';
import { usePermissions } from '@/common/auth/use-session';
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
import { Switch } from '@/common/components/ui/switch';
import { applyApiErrors } from '@/common/forms/api-errors';

import { useSettings, useSettingsMutations } from './hooks';
import { FeatureSettingsSkeleton, StandupSettingsSkeleton } from './loading';

type Standup = Awaited<
  ReturnType<typeof api.standups.listStandups>
>['data'][number];
type DigestInput = Pick<
  Parameters<typeof api.standups.updateStandup>[1],
  'manager_email' | 'manager_digest_enabled'
>;

const featureNames: Record<string, string> = {
  standup: 'Standups',
  connect: 'Coffee chats',
  kudos: 'Kudos',
  insights: 'Insights',
  mcp: 'MCP',
  google_chat: 'Google Chat',
};

const featureDescriptions: Record<string, string> = {
  standup: 'Collect updates from your team and share the summary.',
  connect: 'Introduce people from a channel on a regular cadence.',
  kudos: 'Peer recognition with a daily allowance.',
  insights: 'See who needs recognition and where blockers persist.',
  mcp: 'Connect an AI assistant to your workspace data.',
  google_chat: 'Mirror standups into Google Chat.',
};

function DigestSettings({ standup }: { standup: Standup }) {
  const { canAdminister } = usePermissions();
  const { digest } = useSettingsMutations();

  const form = useForm<DigestInput>({
    defaultValues: {
      manager_email: standup.manager_email ?? '',
      manager_digest_enabled: standup.manager_digest_enabled ?? false,
    },
  });

  const editable = canAdminister('standup');

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mail className="size-4 text-muted-foreground" />
          Manager digest
        </CardTitle>
        <CardDescription>
          Send the workspace’s daily answers to a manager after the reporting
          window.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          onSubmit={form.handleSubmit(async (body) => {
            try {
              await digest.mutateAsync({ id: standup.id, body });
              toast.success('Digest settings saved');
            } catch (error) {
              applyApiErrors(error, form.setError);
            }
          })}
        >
          <label className="flex flex-col gap-2 text-sm font-medium">
            Manager email
            <Input
              type="email"
              placeholder="manager@company.com"
              disabled={!editable}
              {...form.register('manager_email', {
                validate: (value) =>
                  !form.getValues('manager_digest_enabled') ||
                  !!value ||
                  'Enter an email before enabling the digest.',
              })}
            />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              disabled={!editable}
              {...form.register('manager_digest_enabled')}
            />
            Send a daily digest
          </label>
          {form.formState.errors.manager_email && (
            <p role="alert" className="text-sm text-destructive">
              {form.formState.errors.manager_email.message}
            </p>
          )}
          {form.formState.errors.root && (
            <p role="alert" className="text-sm text-destructive">
              {form.formState.errors.root.message ??
                form.formState.errors.root.server?.message}
            </p>
          )}
          {editable ? (
            <Button type="submit" disabled={digest.isPending}>
              {digest.isPending ? 'Saving…' : 'Save changes'}
            </Button>
          ) : (
            <p className="text-xs text-muted-foreground">
              A standup administrator can change these settings.
            </p>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

export function SettingsPage() {
  const { standups, modules } = useSettings();
  const { module, feed } = useSettingsMutations();
  const { isAdmin, canAdminister } = usePermissions();

  const first = standups.data?.[0];
  const feedUrl = first?.feed_token
    ? `${window.location.origin}/feed/${encodeURIComponent(first.feed_token)}`
    : '';

  return (
    <div className="page">
      <PageHeader
        title="Settings"
        description="Make Morgenruf work for your workspace."
      />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Puzzle className="size-4 text-muted-foreground" />
              Features
            </CardTitle>
            <CardDescription>
              Switch a feature off to stop it running and remove it from
              navigation. Your data stays saved.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <LoadingTransition pending={modules.isPending}>
              {modules.isPending ? (
                <FeatureSettingsSkeleton />
              ) : modules.error ? (
                <ErrorState
                  error={modules.error}
                  retry={() => modules.refetch()}
                />
              ) : (
                <div className="divide-y">
                  {modules.data
                    ?.filter((item) => item.available !== false)
                    .map((item) => (
                      <div
                        key={item.name}
                        className="flex items-start justify-between gap-4 py-4 first:pt-0 last:pb-0"
                      >
                        <div className="space-y-1">
                          <p className="text-sm font-medium">
                            {featureNames[item.name] ?? item.name}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {featureDescriptions[item.name]}
                          </p>
                          {!!item.missing_scopes?.length && (
                            <p className="text-xs text-amber-600">
                              Needs Slack permissions:{' '}
                              {item.missing_scopes.join(', ')}.{' '}
                              <a href="/install" className="underline">
                                Re-authorise Slack
                              </a>
                            </p>
                          )}
                        </div>
                        {isAdmin && !item.missing_scopes?.length ? (
                          <Switch
                            checked={item.active}
                            aria-label={`${featureNames[item.name] ?? item.name} enabled`}
                            className="mt-0.5"
                            disabled={module.isPending}
                            onCheckedChange={(enabled) =>
                              module.mutate(
                                { name: item.name, enabled },
                                {
                                  onSuccess: () =>
                                    toast.success(
                                      `${featureNames[item.name] ?? item.name} ${enabled ? 'enabled' : 'disabled'}`,
                                    ),
                                  onError: (error) =>
                                    toast.error(errorMessage(error)),
                                },
                              )
                            }
                          />
                        ) : (
                          <Badge variant="secondary">
                            {item.missing_scopes?.length
                              ? 'Unavailable'
                              : item.active
                                ? 'On'
                                : 'Off'}
                          </Badge>
                        )}
                      </div>
                    ))}
                </div>
              )}
            </LoadingTransition>
          </CardContent>
        </Card>
        <LoadingTransition
          pending={standups.isPending}
          className="*:data-[slot=card]:h-full"
        >
          {standups.isPending ? (
            <StandupSettingsSkeleton />
          ) : standups.error ? (
            <ErrorState
              error={standups.error}
              retry={() => standups.refetch()}
            />
          ) : first ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Settings2 className="size-4 text-muted-foreground" />
                  Standup schedule
                </CardTitle>
                <CardDescription>{first.name}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm">
                  {first.schedule_time} {first.schedule_tz} ·{' '}
                  {first.schedule_days.join(', ')}
                </p>
                <p className="text-sm text-muted-foreground">
                  {first.participants.length
                    ? `${first.participants.length} participants`
                    : 'Everyone in the channel'}
                </p>
                {first.registration_error ? (
                  <p
                    role="alert"
                    className="rounded-md bg-destructive/10 p-3 text-sm text-destructive"
                  >
                    <strong>This standup never runs.</strong>{' '}
                    {first.registration_error}
                  </p>
                ) : first.next_run ? (
                  <p className="text-sm text-muted-foreground">
                    Next run: {new Date(first.next_run).toLocaleString()}
                  </p>
                ) : (
                  <Badge variant="secondary" className="me-2">
                    {first.active ? 'No next run scheduled' : 'Paused'}
                  </Badge>
                )}
                <Link
                  to={
                    canAdminister('standup')
                      ? `/dashboard/standups?edit=${first.id}`
                      : '/dashboard/standups'
                  }
                  className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
                >
                  {canAdminister('standup')
                    ? 'Edit this standup'
                    : 'View standups'}
                  <ExternalLink className="size-3.5" />
                </Link>
                {(standups.data?.length ?? 0) > 1 && (
                  <p className="text-xs text-muted-foreground">
                    {standups.data!.length - 1} more schedules on the Standups
                    page.
                  </p>
                )}
              </CardContent>
            </Card>
          ) : (
            <EmptyState
              title="No standup configured"
              description="Create a standup to configure daily digest and public feed settings."
              action={
                canAdminister('standup') && (
                  <Link
                    to="/dashboard/standups?new=true"
                    className="text-sm font-medium text-primary"
                  >
                    Create a standup
                  </Link>
                )
              }
            />
          )}
        </LoadingTransition>
        {(standups.isPending || (!standups.error && first)) && (
          <>
            <LoadingTransition
              pending={standups.isPending}
              className="[&>[data-slot=card]]:h-full"
            >
              {standups.isPending ? (
                <StandupSettingsSkeleton section="feed" />
              ) : (
                first && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <Globe className="size-4 text-muted-foreground" />
                        Public standup feed
                      </CardTitle>
                      <CardDescription>
                        A read-only link to today’s standups. Anyone with the
                        link can read it without signing in.
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm">Enable public feed</span>
                        {isAdmin ? (
                          <Switch
                            checked={!!first.feed_public}
                            aria-label="Public standup feed enabled"
                            disabled={feed.isPending}
                            onCheckedChange={(enabled) =>
                              feed.mutate(enabled, {
                                onSuccess: () =>
                                  toast.success(
                                    enabled
                                      ? 'Public feed enabled'
                                      : 'Public feed disabled',
                                  ),
                                onError: (error) =>
                                  toast.error(errorMessage(error)),
                              })
                            }
                          />
                        ) : (
                          <Badge variant="secondary">
                            {first.feed_public ? 'On' : 'Off'}
                          </Badge>
                        )}
                      </div>
                      {first.feed_public && feedUrl && (
                        <div className="flex gap-2">
                          <Input
                            aria-label="Public feed URL"
                            readOnly
                            value={feedUrl}
                          />
                          <Button
                            variant="outline"
                            size="icon"
                            aria-label="Copy public feed URL"
                            onClick={() =>
                              navigator.clipboard
                                .writeText(feedUrl)
                                .then(() => toast.success('Feed URL copied'))
                                .catch(() =>
                                  toast.error(
                                    'Copy unavailable. Select and copy the URL.',
                                  ),
                                )
                            }
                          >
                            <Copy className="size-4" />
                          </Button>
                          <a
                            className="inline-flex items-center rounded-md border px-3"
                            href={feedUrl}
                            target="_blank"
                            rel="noreferrer"
                            aria-label="Open public feed"
                          >
                            <ExternalLink className="size-4" />
                          </a>
                        </div>
                      )}
                      {first.feed_public && !feedUrl && isAdmin && (
                        <Button
                          disabled={feed.isPending}
                          onClick={() =>
                            feed.mutate(true, {
                              onError: (error) =>
                                toast.error(errorMessage(error)),
                            })
                          }
                        >
                          Generate feed URL
                        </Button>
                      )}
                      {!isAdmin && (
                        <p className="text-xs text-muted-foreground">
                          Only workspace administrators can publish the feed.
                        </p>
                      )}
                    </CardContent>
                  </Card>
                )
              )}
            </LoadingTransition>
            <LoadingTransition
              pending={standups.isPending}
              className="[&>[data-slot=card]]:h-full"
            >
              {standups.isPending ? (
                <StandupSettingsSkeleton section="digest" />
              ) : (
                first && (
                  <DigestSettings
                    key={`${first.id}-${first.manager_email}-${first.manager_digest_enabled}`}
                    standup={first}
                  />
                )
              )}
            </LoadingTransition>
          </>
        )}
      </div>
    </div>
  );
}

export default SettingsPage;
