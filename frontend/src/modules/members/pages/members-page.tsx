import { useState } from 'react';
import { RefreshCw, UserPlus } from 'lucide-react';
import { useSearchParams } from 'react-router';
import { toast } from 'sonner';

import {
  LoadingField,
  SkeletonPeople,
  SkeletonRegion,
} from '@/common/components/loading-skeleton';
import { EmptyState, ErrorState, PageHeader } from '@/common/components/page';
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
import { Skeleton } from '@/common/components/ui/skeleton';

import { useMembers } from '../hooks';
import { MembersSkeleton } from '../loading';

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
  const [params, setParams] = useSearchParams();
  const [inviting, setInviting] = useState(false);
  const [inviteSearch, setInviteSearch] = useState('');
  const [inviteId, setInviteId] = useState('');

  const channel = params.get('channel') ?? '';
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
  const q = (params.get('q') ?? '').trim().toLowerCase();

  const filtered = all
    .filter((member) => {
      const text =
        `${member.name} ${member.display_name} ${member.email} ${member.id}`.toLowerCase();

      return (
        text.includes(q) &&
        (!params.get('role') || member.role === params.get('role')) &&
        (!params.get('tracking') ||
          (params.get('tracking') === 'tracked'
            ? member.tracked !== false
            : member.tracked === false))
      );
    })
    .sort((a, b) => {
      const nameOrder = (a.name || a.display_name || a.id).localeCompare(
        b.name || b.display_name || b.id,
      );

      if (params.get('sort') === 'role')
        return (
          Number(b.role === 'admin') - Number(a.role === 'admin') || nameOrder
        );

      if (params.get('sort') === 'timezone')
        return (a.tz ?? 'UTC').localeCompare(b.tz ?? 'UTC') || nameOrder;

      return nameOrder;
    });

  function filter(name: string, value: string) {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);

        if (value) next.set(name, value);
        else next.delete(name);

        return next;
      },
      { replace: true },
    );
  }

  const grantable = (modules.data ?? []).filter(
    (module) => module.available !== false && module.active && module.delegable,
  );

  const busy = role.isPending || grant.isPending;

  return (
    <div className="page">
      <PageHeader
        title="Members"
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
          value={params.get('q') ?? ''}
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
          value={params.get('role') ?? ''}
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
          value={params.get('tracking') ?? ''}
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
          value={params.get('sort') ?? ''}
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
                        <div className="flex size-11 shrink-0 items-center justify-center relative overflow-hidden rounded-full bg-primary/10 font-semibold text-primary">
                          {name
                            .split(/\s+/)
                            .map((word) => word[0])
                            .slice(0, 2)
                            .join('')}
                          {member.avatar && (
                            <img
                              src={member.avatar}
                              alt=""
                              className="absolute inset-0 size-full object-cover"
                              loading="lazy"
                              onError={(event) => {
                                event.currentTarget.style.display = 'none';
                              }}
                            />
                          )}
                        </div>
                        <div className="min-w-0">
                          <h2 className="truncate font-medium">{name}</h2>
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
                                  !!member.module_admin?.includes(module.name);

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
      <Dialog open={inviting} onOpenChange={setInviting}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Invite a workspace admin</DialogTitle>
            <DialogDescription>
              Choose someone in Slack to give them workspace administration
              access.
            </DialogDescription>
          </DialogHeader>
          <Input
            aria-label="Find a member to invite"
            placeholder="Search members…"
            value={inviteSearch}
            onChange={(event) => setInviteSearch(event.target.value)}
          />
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
            <div className="max-h-72 space-y-2 overflow-y-auto">
              {inviteMembers.data
                ?.filter((member) =>
                  `${member.name} ${member.display_name} ${member.email}`
                    .toLowerCase()
                    .includes(inviteSearch.toLowerCase()),
                )
                .map((member) => (
                  <Button
                    key={member.id}
                    variant={inviteId === member.id ? 'secondary' : 'outline'}
                    aria-pressed={inviteId === member.id}
                    className="h-auto w-full justify-between py-3"
                    disabled={invite.isPending || member.role === 'admin'}
                    onClick={() => setInviteId(member.id)}
                  >
                    <span>{member.name || member.id}</span>
                    <span className="text-xs text-muted-foreground">
                      {member.role === 'admin' ? 'Already admin' : member.email}
                    </span>
                  </Button>
                ))}
            </div>
          )}
          <div className="flex justify-end gap-2">
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
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
