import { useState, type ReactNode } from 'react';
import {
  ArrowLeft,
  CalendarDays,
  Coffee,
  Play,
  Plus,
  Trash,
  Users,
} from 'lucide-react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import { toast } from 'sonner';

import { errorMessage } from '@/common/api/errors';
import { usePermissions } from '@/common/auth/use-session';
import { EmptyState, ErrorState, PageHeader } from '@/common/components/page';
import { Badge } from '@/common/components/ui/badge';
import { Button } from '@/common/components/ui/button';
import { Card, CardContent } from '@/common/components/ui/card';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/common/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/common/components/ui/select';

import { Attendance } from './attendance';
import { cadenceLabel } from './form-utils';
import {
  useConnect,
  useConnectCapabilities,
  useConnectMutations,
  useConnectResources,
  type Program,
} from './hooks';
import {
  ConnectAttendanceSkeleton,
  ConnectDetailSkeleton,
  ConnectListSkeleton,
  ProgramFormSkeleton,
} from './loading';
import { ProgramForm } from './program-form';

function ConnectGate({
  children,
  loadingFallback,
}: {
  children: ReactNode;
  loadingFallback: ReactNode;
}) {
  const query = useConnectCapabilities();
  const { isAdmin } = usePermissions();
  const { enable } = useConnectMutations();

  if (query.isPending) return loadingFallback;

  if (query.error)
    return <ErrorState error={query.error} retry={() => query.refetch()} />;

  const feature = query.data?.find((item) => item.name === 'connect');

  if (!feature || feature.available === false)
    return (
      <EmptyState
        title="Coffee chats are unavailable"
        description="This deployment does not include the coffee chat module."
      />
    );

  if (feature.missing_scopes?.length)
    return (
      <EmptyState
        title="Coffee chats need more Slack access"
        description={
          <>
            Morgenruf needs permission to open group messages and check for
            replies.
            <br />
            Missing: {feature.missing_scopes.join(', ')}
          </>
        }
        action={
          isAdmin && (
            <a
              href="/install"
              className="text-sm font-medium text-primary underline"
            >
              Re-authorise Slack
            </a>
          )
        }
      />
    );

  if (!feature.active)
    return (
      <EmptyState
        title="Coffee chats are switched off"
        description={
          isAdmin
            ? 'Turn on introductions for your workspace. Nothing is sent until you create a coffee chat.'
            : 'A workspace administrator can turn coffee chats on in Settings.'
        }
        action={
          isAdmin && (
            <Button
              disabled={enable.isPending}
              onClick={() =>
                enable.mutate(undefined, {
                  onSuccess: () => toast.success('Coffee chats enabled'),
                  onError: (error) => toast.error(errorMessage(error)),
                })
              }
            >
              {enable.isPending ? 'Enabling…' : 'Turn on coffee chats'}
            </Button>
          )
        }
      />
    );

  return children;
}

function ProgramActions({ program }: { program: Program }) {
  const { canAdminister } = usePermissions();
  const { save, remove, run } = useConnectMutations();
  const navigate = useNavigate();
  const [runOpen, setRunOpen] = useState(false);

  if (!canAdminister('connect')) return null;

  return (
    <div className="flex flex-wrap gap-2">
      <Dialog
        open={runOpen}
        onOpenChange={(open) => {
          if (!run.isPending) setRunOpen(open);
        }}
      >
        <DialogTrigger
          render={<Button size="sm" variant="outline" />}
          disabled={run.isPending}
        >
          <Play className="size-3.5" />
          Run a round
        </DialogTrigger>
        <DialogContent showCloseButton={!run.isPending}>
          <DialogHeader>
            <DialogTitle>Send introductions now?</DialogTitle>
            <DialogDescription>
              Everyone in the channel will receive a group DM.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose
              render={<Button variant="outline" />}
              disabled={run.isPending}
            >
              Cancel
            </DialogClose>
            <Button
              disabled={run.isPending}
              onClick={() =>
                run.mutate(program.id, {
                  onSuccess: () => {
                    setRunOpen(false);
                    toast.success('Introductions sent');
                  },
                  onError: (error) => toast.error(errorMessage(error)),
                })
              }
            >
              {run.isPending ? 'Starting…' : 'Run a round'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Button
        size="sm"
        variant="outline"
        disabled={save.isPending}
        onClick={() =>
          save.mutate(
            { id: program.id, body: { enabled: !program.enabled } },
            {
              onSuccess: () =>
                toast.success(
                  program.enabled
                    ? 'Introductions paused'
                    : 'Introductions resumed',
                ),
              onError: (error) => toast.error(errorMessage(error)),
            },
          )
        }
      >
        {program.enabled ? 'Pause' : 'Resume'}
      </Button>
      <Button
        size="icon-sm"
        variant="destructiveGhost"
        disabled={remove.isPending}
        onClick={() => {
          if (
            window.confirm(
              `Delete ${program.name}? Its past rounds will also be deleted.`,
            )
          )
            remove.mutate(program.id, {
              onSuccess: () => {
                toast.success('Coffee chat deleted');
                navigate('/dashboard/connect');
              },
              onError: (error) => toast.error(errorMessage(error)),
            });
        }}
      >
        <Trash />
        <span className="sr-only">Delete</span>
      </Button>
    </div>
  );
}

function ProgramList() {
  const query = useConnect();
  const { channels, zoom } = useConnectResources();
  const { canAdminister } = usePermissions();

  if (query.isPending) return <ConnectListSkeleton />;

  if (query.error)
    return <ErrorState error={query.error} retry={() => query.refetch()} />;

  if (!query.data?.length)
    return (
      <EmptyState
        title="Make room for a conversation"
        description="Pick a channel and a cadence. Morgenruf introduces people in a group DM, giving them a simple way to meet."
        action={
          canAdminister('connect') && (
            <Link
              className="text-sm font-medium text-primary"
              to="/dashboard/connect/new"
            >
              Create the first coffee chat
            </Link>
          )
        }
      />
    );

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        {query.data.map((program) => (
          <Card key={program.id}>
            <CardContent className="flex flex-col gap-4 p-5 sm:flex-row">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Coffee className="size-5" />
              </div>
              <div className="min-w-0 flex-1 space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    to={`/dashboard/connect/${program.id}`}
                    className="font-semibold hover:text-primary"
                  >
                    {program.name}
                  </Link>
                  <Badge variant={program.enabled ? 'default' : 'secondary'}>
                    {program.enabled ? 'Running' : 'Paused'}
                  </Badge>
                </div>
                <p className="text-sm text-muted-foreground">
                  #
                  {channels.data?.find(
                    (channel) => channel.id === program.channel_id,
                  )?.name ?? program.channel_id}
                </p>
                <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <CalendarDays className="size-3.5" />
                    {cadenceLabel(program)} · {program.timezone}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Users className="size-3.5" />
                    {program.pool_size == null
                      ? 'Pool size unavailable'
                      : `${program.pool_size} in the pool`}
                  </span>
                </div>
                {program.next_round_date && (
                  <p className="text-xs text-muted-foreground">
                    Next round:{' '}
                    {new Date(program.next_round_date).toLocaleDateString()}
                  </p>
                )}
                <div className="flex flex-wrap items-center gap-4">
                  <Link
                    to={`/dashboard/connect/${program.id}`}
                    className="text-sm font-medium text-primary"
                  >
                    {canAdminister('connect')
                      ? 'Settings & members'
                      : 'View details'}
                  </Link>
                  <Link
                    to={`/dashboard/connect/attendance?program=${program.id}`}
                    className="text-sm font-medium text-primary"
                  >
                    Attendance
                  </Link>
                </div>
              </div>
              <ProgramActions program={program} />
            </CardContent>
          </Card>
        ))}
      </div>
      {zoom.data?.configured && (
        <p className="text-xs text-muted-foreground">
          {zoom.data.linked} people have linked Zoom
          {zoom.data.needs_reconnect
            ? ` · ${zoom.data.needs_reconnect} need to reconnect`
            : ''}
          .
        </p>
      )}
      <div className="space-y-4">
        <h2 className="font-semibold">
          {query.data[0].name} · recent attendance
        </h2>
        <Attendance programId={query.data[0].id} />
      </div>
    </div>
  );
}

export function ConnectListPage() {
  const { canAdminister } = usePermissions();
  const navigate = useNavigate();

  return (
    <div className="page">
      <PageHeader
        title="Coffee chats"
        description="Small conversations that bring your team closer."
        actions={
          canAdminister('connect') && (
            <Button onClick={() => navigate('/dashboard/connect/new')}>
              <Plus className="size-4" />
              New coffee chat
            </Button>
          )
        }
      />
      <ConnectGate loadingFallback={<ConnectListSkeleton />}>
        <ProgramList />
      </ConnectGate>
    </div>
  );
}

export function ConnectNewPage() {
  const { canAdminister } = usePermissions();

  return (
    <div className="page">
      <PageHeader
        title="New coffee chat"
        description="Create a regular invitation to get to know someone."
        actions={
          <Link
            to="/dashboard/connect"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground"
          >
            <ArrowLeft className="size-4" />
            All coffee chats
          </Link>
        }
      />
      <ConnectGate loadingFallback={<ProgramFormSkeleton />}>
        {canAdminister('connect') ? (
          <ProgramForm />
        ) : (
          <EmptyState
            title="Administrator access required"
            description="A coffee chat administrator can create an introduction program."
          />
        )}
      </ConnectGate>
    </div>
  );
}

function ProgramDetail() {
  const { programId } = useParams();
  const query = useConnect();

  if (query.isPending) return <ConnectDetailSkeleton />;

  if (query.error)
    return <ErrorState error={query.error} retry={() => query.refetch()} />;

  const program = query.data?.find((item) => String(item.id) === programId);

  if (!program)
    return (
      <EmptyState
        title="Coffee chat not found"
        description="It may have been deleted, or you may be viewing another workspace."
        action={
          <Link to="/dashboard/connect" className="text-primary">
            Back to coffee chats
          </Link>
        }
      />
    );

  return (
    <>
      <PageHeader
        title={program.name}
        description={cadenceLabel(program)}
        actions={<ProgramActions program={program} />}
      />
      <ProgramForm key={program.id} program={program} />
      <Link
        to={`/dashboard/connect/attendance?program=${program.id}`}
        className="inline-block text-sm font-medium text-primary"
      >
        View attendance →
      </Link>
    </>
  );
}

export function ConnectDetailPage() {
  return (
    <div className="page">
      <Link
        to="/dashboard/connect"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground"
      >
        <ArrowLeft className="size-4" />
        All coffee chats
      </Link>
      <ConnectGate loadingFallback={<ConnectDetailSkeleton />}>
        <ProgramDetail />
      </ConnectGate>
    </div>
  );
}

function AttendancePageContent() {
  const query = useConnect();
  const [params, setParams] = useSearchParams();

  if (query.isPending) return <ConnectAttendanceSkeleton />;

  if (query.error)
    return <ErrorState error={query.error} retry={() => query.refetch()} />;

  if (!query.data?.length)
    return (
      <EmptyState
        title="Create a coffee chat first"
        description="Round attendance will appear after the first introductions."
      />
    );

  const programOptions = query.data.map((program) => ({
    value: program.id,
    label: program.name,
  }));
  const selected =
    query.data.find(
      (program) => String(program.id) === params.get('program'),
    ) ?? query.data[0];

  return (
    <div className="space-y-6">
      <label className="grid max-w-sm gap-2 text-sm font-medium">
        Coffee chat
        <Select
          items={programOptions}
          value={selected.id}
          onValueChange={(value) => {
            if (value !== null) setParams({ program: String(value) });
          }}
        >
          <SelectTrigger aria-label="Coffee chat" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {programOptions.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>
      <Attendance key={selected.id} programId={selected.id} />
    </div>
  );
}

export function ConnectAttendancePage() {
  return (
    <div className="page">
      <PageHeader
        title="Coffee chat attendance"
        description="Who was introduced, who met, and where a nudge might help."
      />
      <ConnectGate loadingFallback={<ConnectAttendanceSkeleton />}>
        <AttendancePageContent />
      </ConnectGate>
    </div>
  );
}

export default ConnectListPage;
