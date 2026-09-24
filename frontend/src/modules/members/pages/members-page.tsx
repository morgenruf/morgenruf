import { useState } from 'react';
import { getRouteApi } from '@tanstack/react-router';
import { RefreshCw, UserPlus } from 'lucide-react';
import { toast } from 'sonner';

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

import { useMembers } from '../hooks';
import { MembersSkeleton } from '../loading';
import { validateSearch, type Search } from '../search';

const moduleLabels: Record<string, string> = {
  standup: 'Standups',
  connect: 'Coffee chats',
  kudos: 'Kudos',
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

  const [inviting, setInviting] = useState(false);
  const [inviteSearch, setInviteSearch] = useState('');
  const [inviteId, setInviteId] = useState('');

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
  } = useMembers(channel, inviting);

  const channelOptions = [
    { value: '', label: 'All channels' },
    ...(channels.data ?? []).map((channel) => ({
      value: channel.id,
      label: `#${channel.name}`,
    })),
  ];

  const isAdmin = session?.role === 'admin';
  const all = members.data ?? [];
  const q = (params.q ?? '').trim().toLowerCase();

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

  const grantable = (modules.data ?? []).filter(
    (module) => module.available !== false && module.active && module.delegable,
  );

  const busy = role.isPending || grant.isPending;

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
          value={params.q ?? ''}
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
              {filtered.length} of {all.length} members ·{' '}
              {all.filter((member) => member.tracked !== false).length} in
              Morgenruf. People not tracked by Morgenruf do not appear in
              participation figures.
            </p>
            {!filtered.length ? (
              <EmptyState
                title={
                  all.length
                    ? 'No members match these filters'
                    : 'No members found'
                }
                description="Members are synchronized from your Slack workspace."
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
                              <SkeletonRegion label="Loading standup enrollment…">
                                <Skeleton className="h-4 w-24" />
                              </SkeletonRegion>
                            ) : (
                              <p>
                                {count
                                  ? `${count} standup${count === 1 ? '' : 's'}`
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
                                        grant.mutate({
                                          id: member.id,
                                          module: module.name,
                                          enabled: !active,
                                        })
                                      }
                                    >
                                      {moduleLabels[module.name] ?? module.name}
                                    </Button>
                                  );
                                })}
                            </div>
                          </div>
                        )}
                        {isAdmin && member.id !== session?.user_id && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="w-full"
                            disabled={busy}
                            onClick={() =>
                              role.mutate({
                                id: member.id,
                                role:
                                  member.role === 'admin' ? 'member' : 'admin',
                              })
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
