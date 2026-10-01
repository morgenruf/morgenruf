import { useState } from 'react';
import { getRouteApi, useLocation } from '@tanstack/react-router';
import { CalendarPlus, Mail, RefreshCw, UserPlus } from 'lucide-react';
import { toast } from 'sonner';

import { AskForDatesDialog } from '@/common/components/ask-for-dates-dialog';
import {
  LoadingField,
  SkeletonPeople,
  SkeletonRegion,
} from '@/common/components/loading-skeleton';
import { LoadingTransition } from '@/common/components/loading-transition';
import { EmptyState, ErrorState, PageHeader } from '@/common/components/page';
import { Person, PersonAvatar } from '@/common/components/person';
import { Badge } from '@/common/components/ui/badge';
import { Button } from '@/common/components/ui/button';
import { Card, CardContent } from '@/common/components/ui/card';
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
import { ScrollArea } from '@/common/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/common/components/ui/select';
import { Skeleton } from '@/common/components/ui/skeleton';
import { useConfirm } from '@/common/hooks/use-confirm';
import { plural } from '@/common/lib/format';
import { hasDates, profileFacts } from '@/common/lib/profile';

import { useMembers } from '../hooks';
import { MembersSkeleton } from '../loading';
import { EditProfileDialog, ImportDatesDialog } from '../profile-dialogs';
import { validateSearch, type Search } from '../search';

const moduleLabels: Record<string, string> = {
  standup: 'Standups',
  connect: 'Coffee chats',
  kudos: 'Kudos',
  polls: 'Polls',
  celebrations: 'Celebrations',
  insights: 'Insights',
};

const roleOptions = [
  { value: '', label: 'All roles' },
  { value: 'admin', label: 'Admins' },
  { value: 'member', label: 'Members' },
];

const trackingOptions = [
  { value: '', label: 'Everyone in Slack' },
  { value: 'tracked', label: 'In Morgenruf' },
  { value: 'untracked', label: 'Not in Morgenruf' },
];

const sortOptions = [
  { value: '', label: 'Sort by name' },
  { value: 'role', label: 'Sort by role' },
  { value: 'timezone', label: 'Sort by timezone' },
];

export default function MembersPage() {
  const route = getRouteApi('/dashboard/_authenticated/members');
  const params = route.useSearch();
  const navigate = route.useNavigate();

  // Route search commits after loaders; typing needs the latest URL immediately.
  const search = useLocation({
    select: (location) => validateSearch.shape.q.parse(location.search.q),
  });

  const [inviting, setInviting] = useState(false);
  const [inviteSearch, setInviteSearch] = useState('');
  const [inviteId, setInviteId] = useState('');
  const [importing, setImporting] = useState(false);
  const [asking, setAsking] = useState(false);
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(
    null,
  );

  const channel = params.channel ?? '';

  const {
    members,
    inviteMembers,
    channels,
    modules,
    standups,
    role,
    grant,
    invite,
    session,
    profiles,
    saveProfile,
    importDates,
  } = useMembers(channel, inviting);

  const profileById = new Map(
    (profiles.data ?? []).map((profile) => [profile.user_id, profile]),
  );

  const channelOptions = [
    { value: '', label: 'All channels' },
    ...(channels.data ?? []).map((channel) => ({
      value: channel.id,
      label: `#${channel.name}`,
    })),
  ];

  const isAdmin = session?.role === 'admin';
  // Asking people for dates only makes sense once something celebrates them.
  const celebrationsActive = !!modules.data?.find(
    (module) => module.name === 'celebrations',
  )?.active;
  const all = members.data ?? [];
  const q = search.trim().toLowerCase();

  const filtered = all
    .filter((member) => {
      const text =
        `${member.name} ${member.display_name} ${member.email} ${member.id}`.toLowerCase();

      return (
        text.includes(q) &&
        (!params.role || member.role === params.role) &&
        (!params.tracking ||
          (params.tracking === 'tracked'
            ? member.tracked !== false
            : member.tracked === false))
      );
    })
    .sort((a, b) => {
      const nameOrder = (a.name || a.display_name || a.id).localeCompare(
        b.name || b.display_name || b.id,
      );

      if (params.sort === 'role')
        return (
          Number(b.role === 'admin') - Number(a.role === 'admin') || nameOrder
        );

      if (params.sort === 'timezone')
        return (a.tz ?? 'UTC').localeCompare(b.tz ?? 'UTC') || nameOrder;

      return nameOrder;
    });

  function filter(name: keyof Search, value: string) {
    void navigate({
      search: (previous) =>
        validateSearch.parse({ ...previous, [name]: value }),
      replace: true,
      resetScroll: false,
    });
  }

  const hasFilters = !!(
    search ||
    params.channel ||
    params.role ||
    params.tracking
  );

  function clearFilters() {
    void navigate({
      search: (previous) =>
        validateSearch.parse({
          ...previous,
          q: '',
          channel: '',
          role: '',
          tracking: '',
        }),
      replace: true,
      resetScroll: false,
    });
  }

  const grantable = (modules.data ?? []).filter(
    (module) => module.available !== false && module.active && module.delegable,
  );

  const busy = role.isPending || grant.isPending;
  const { confirm, dialog } = useConfirm();

  async function changeRole(id: string, name: string, admin: boolean) {
    const ok = await confirm(
      admin
        ? {
            title: `Make ${name} an admin?`,
            description:
              'Admins can change every feature, workspace setting and role, including yours.',
            confirmLabel: 'Make admin',
          }
        : {
            title: `Make ${name} a member?`,
            description:
              'They lose access to workspace settings and to every feature they do not run.',
            confirmLabel: 'Make member',
            destructive: true,
          },
    );
    if (ok) role.mutate({ id, role: admin ? 'admin' : 'member' });
  }

  async function changeGrant(
    id: string,
    name: string,
    module: string,
    enabled: boolean,
  ) {
    const label = moduleLabels[module] ?? module;
    if (
      !enabled &&
      !(await confirm({
        title: `Take ${label} away from ${name}?`,
        description: `${name} will no longer be able to change ${label} settings.`,
        confirmLabel: 'Remove access',
        destructive: true,
      }))
    )
      return;
    grant.mutate({ id, module, enabled });
  }

  return (
    <div className="page">
      <PageHeader
        title="Members"
        reserveActionSpace
        description="Your Slack workspace, and the people who run each feature."
        actions={
          <>
            <Button
              variant="outline"
              disabled={members.isFetching}
              onClick={() => void members.refetch()}
            >
              <RefreshCw /> Refresh
            </Button>
            {isAdmin && (
              <Button
                onClick={() => {
                  setInviteId('');
                  setInviteSearch('');
                  setInviting(true);
                }}
              >
                <UserPlus /> Invite admin
              </Button>
            )}
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Input
          aria-label="Search members"
          placeholder="Search name, handle or email"
          value={search}
          onChange={(event) => filter('q', event.target.value)}
        />
        <LoadingField
          pending={channels.isPending}
          label="Loading channel filter…"
        >
          <Select
            items={channelOptions}
            value={channel}
            onValueChange={(value) => filter('channel', value ?? '')}
          >
            <SelectTrigger aria-label="Filter by channel" className="w-full">
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
        <Select
          items={roleOptions}
          value={params.role ?? ''}
          onValueChange={(value) => filter('role', value ?? '')}
        >
          <SelectTrigger aria-label="Filter by role" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {roleOptions.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          items={trackingOptions}
          value={params.tracking ?? ''}
          onValueChange={(value) => filter('tracking', value ?? '')}
        >
          <SelectTrigger aria-label="Filter by tracking" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {trackingOptions.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          items={sortOptions}
          value={params.sort ?? ''}
          onValueChange={(value) => filter('sort', value ?? '')}
        >
          <SelectTrigger aria-label="Sort members" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {sortOptions.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <LoadingTransition pending={members.isPending}>
        {members.isPending ? (
          <MembersSkeleton />
        ) : members.isError ? (
          <ErrorState
            error={members.error}
            retry={() => void members.refetch()}
          />
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              {filtered.length} of {plural(all.length, 'member')} ·{' '}
              {all.filter((member) => member.tracked !== false).length} in
              Morgenruf. People not tracked by Morgenruf do not appear in
              participation figures.
            </p>
            {isAdmin && (
              <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                {profiles.isSuccess && (
                  <p>
                    {
                      all.filter((member) =>
                        hasDates(profileById.get(member.id)),
                      ).length
                    }{' '}
                    of {all.length} have a birthday or start date on file.
                  </p>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setImporting(true)}
                >
                  <CalendarPlus /> Import dates
                </Button>
                {celebrationsActive && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setAsking(true)}
                  >
                    <Mail /> Ask for dates
                  </Button>
                )}
              </div>
            )}
            {!filtered.length ? (
              <EmptyState
                title={
                  all.length
                    ? 'No members match these filters'
                    : 'No members found'
                }
                description={
                  all.length
                    ? 'Try a different search or filter.'
                    : 'Members are synchronised from your Slack workspace. Try Refresh.'
                }
                action={
                  all.length > 0 &&
                  hasFilters && (
                    <Button variant="outline" onClick={clearFilters}>
                      Clear filters
                    </Button>
                  )
                }
              />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {filtered.map((member) => {
                  const name = member.name || member.display_name || member.id;

                  const count = (standups.data ?? []).filter(
                    (standup) =>
                      !standup.participants?.length ||
                      standup.participants.includes(member.id),
                  ).length;

                  return (
                    <Card key={member.id}>
                      <CardContent className="space-y-4 pt-5">
                        <div className="flex items-center gap-3">
                          <PersonAvatar
                            name={name}
                            avatar={member.avatar}
                            size="large"
                          />
                          <div className="min-w-0">
                            <h2 className="break-words font-medium">{name}</h2>
                            <p className="truncate text-xs text-muted-foreground">
                              @{member.display_name || member.id}
                            </p>
                          </div>
                          <Badge
                            className="ml-auto"
                            variant={
                              member.role === 'admin' ? 'default' : 'secondary'
                            }
                          >
                            {member.role ?? 'member'}
                          </Badge>
                        </div>
                        <div className="space-y-1 text-sm text-muted-foreground">
                          <p>{member.email || 'No email shared'}</p>
                          <p>{member.tz || 'UTC'}</p>
                          <LoadingTransition pending={standups.isPending}>
                            {standups.isPending ? (
                              <SkeletonRegion label="Loading standup enrolment…">
                                <Skeleton className="h-4 w-24" />
                              </SkeletonRegion>
                            ) : (
                              <p>
                                {count
                                  ? plural(count, 'standup')
                                  : member.tracked === false
                                    ? 'Not in Morgenruf'
                                    : 'No standups'}
                              </p>
                            )}
                          </LoadingTransition>
                        </div>
                        {grantable.length > 0 && (
                          <div className="space-y-2 border-t pt-3">
                            <p className="text-xs text-muted-foreground">
                              {member.role === 'admin'
                                ? 'Runs every feature'
                                : (member.module_admin?.length ?? 0)
                                  ? 'Runs'
                                  : isAdmin
                                    ? 'Put in charge of'
                                    : 'Feature access'}
                            </p>
                            <div className="flex flex-wrap gap-2">
                              {grantable
                                .filter(
                                  (module) =>
                                    isAdmin ||
                                    member.role === 'admin' ||
                                    member.module_admin?.includes(module.name),
                                )
                                .map((module) => {
                                  const active =
                                    member.role === 'admin' ||
                                    !!member.module_admin?.includes(
                                      module.name,
                                    );

                                  return (
                                    <Button
                                      key={module.name}
                                      size="sm"
                                      variant={active ? 'secondary' : 'outline'}
                                      aria-pressed={active}
                                      disabled={
                                        !isAdmin ||
                                        member.role === 'admin' ||
                                        busy
                                      }
                                      onClick={() =>
                                        void changeGrant(
                                          member.id,
                                          name,
                                          module.name,
                                          !active,
                                        )
                                      }
                                    >
                                      {moduleLabels[module.name] ?? module.name}
                                    </Button>
                                  );
                                })}
                            </div>
                          </div>
                        )}
                        {isAdmin && profiles.isSuccess && (
                          <div className="space-y-2 border-t pt-3">
                            <p className="text-xs text-muted-foreground">
                              Profile
                            </p>
                            <p className="text-sm">
                              {profileFacts(profileById.get(member.id)).join(
                                ' · ',
                              ) || 'Nothing on file yet'}
                            </p>
                            {profileById.get(member.id)?.celebrate ===
                              false && (
                              <p className="text-xs text-muted-foreground">
                                Asked not to be celebrated publicly
                              </p>
                            )}
                            <Button
                              size="sm"
                              variant="outline"
                              aria-label={`Edit ${name}’s profile`}
                              onClick={() =>
                                setEditing({ id: member.id, name })
                              }
                            >
                              Edit profile
                            </Button>
                          </div>
                        )}
                        {isAdmin && member.id !== session?.user_id && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="w-full"
                            disabled={busy}
                            onClick={() =>
                              void changeRole(
                                member.id,
                                name,
                                member.role !== 'admin',
                              )
                            }
                          >
                            {member.role === 'admin'
                              ? 'Make member'
                              : 'Make admin'}
                          </Button>
                        )}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </>
        )}
      </LoadingTransition>

      {dialog}
      <EditProfileDialog
        member={editing}
        profile={editing ? profileById.get(editing.id) : undefined}
        pending={saveProfile.isPending}
        onSave={(id, data) => saveProfile.mutateAsync({ id, data })}
        onClose={() => setEditing(null)}
      />

      <AskForDatesDialog open={asking} onOpenChange={setAsking} />

      <ImportDatesDialog
        open={importing}
        onOpenChange={setImporting}
        run={(input) => importDates.mutateAsync(input)}
        pending={importDates.isPending}
      />

      <Dialog open={inviting} onOpenChange={setInviting}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Invite a workspace admin</DialogTitle>
            <DialogDescription>
              Choose someone in Slack to give them workspace administration
              access.
            </DialogDescription>
          </DialogHeader>

          <DialogBody>
            <Input
              aria-label="Find a member to invite"
              placeholder="Search members…"
              value={inviteSearch}
              onChange={(event) => setInviteSearch(event.target.value)}
            />
            <LoadingTransition pending={inviteMembers.isPending}>
              {inviteMembers.isPending ? (
                <SkeletonRegion label="Loading members to invite…">
                  <SkeletonPeople rows={5} />
                </SkeletonRegion>
              ) : inviteMembers.isError ? (
                <ErrorState
                  error={inviteMembers.error}
                  retry={() => void inviteMembers.refetch()}
                />
              ) : (
                <ScrollArea
                  className="max-h-72"
                  contentClassName="space-y-2 p-1"
                  viewportProps={{
                    role: 'region',
                    'aria-label': 'Members to invite',
                  }}
                >
                  {inviteMembers.data
                    ?.filter((member) =>
                      `${member.name} ${member.display_name} ${member.email}`
                        .toLowerCase()
                        .includes(inviteSearch.toLowerCase()),
                    )
                    .map((member) => (
                      <Button
                        key={member.id}
                        variant={
                          inviteId === member.id ? 'secondary' : 'outline'
                        }
                        aria-pressed={inviteId === member.id}
                        className="h-auto w-full flex-wrap justify-between py-3 text-left whitespace-normal"
                        disabled={invite.isPending || member.role === 'admin'}
                        onClick={() => setInviteId(member.id)}
                      >
                        <Person
                          {...inviteMembers.person(member.id)}
                          size="compact"
                        />
                        <span className="break-all text-xs text-muted-foreground">
                          {member.role === 'admin'
                            ? 'Already admin'
                            : member.email}
                        </span>
                      </Button>
                    ))}
                </ScrollArea>
              )}
            </LoadingTransition>
          </DialogBody>

          <DialogFooter>
            <Button variant="outline" onClick={() => setInviting(false)}>
              Cancel
            </Button>
            <Button
              disabled={!inviteId || invite.isPending || !isAdmin}
              onClick={() =>
                invite.mutate(
                  { user_id: inviteId, role: 'admin' },
                  {
                    onSuccess: () => {
                      toast.success('Admin invited');
                      setInviting(false);
                      setInviteId('');
                    },
                  },
                )
              }
            >
              {invite.isPending ? 'Granting access…' : 'Grant admin access'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
