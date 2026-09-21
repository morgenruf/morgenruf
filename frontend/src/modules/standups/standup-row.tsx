import { useRef, useState } from 'react';
import {
  AlertCircle,
  ChartNoAxesColumn,
  Clock3,
  MoreHorizontal,
  Pause,
  Play,
  Trash,
  Users,
} from 'lucide-react';
import { toast } from 'sonner';

import { errorMessage } from '@/common/api/errors';
import type { ScheduleParticipation } from '@/common/api/generated/data-contracts';
import { SkeletonRegion } from '@/common/components/loading-skeleton';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/common/components/ui/alert-dialog';
import { Badge } from '@/common/components/ui/badge';
import { Button } from '@/common/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/common/components/ui/dropdown-menu';
import { Skeleton } from '@/common/components/ui/skeleton';
import { cn } from '@/common/lib/utils';

import { healthLabel } from './form-utils';
import { useStandupMutations, type Standup } from './hooks';
import { nextRunLabel, scheduleDays } from './overview-utils';
import { ParticipationSparkline } from './participation-sparkline';

function Participation({
  metrics,
  pending,
  unavailable,
}: {
  metrics?: ScheduleParticipation;
  pending: boolean;
  unavailable: boolean;
}) {
  if (pending)
    return (
      <SkeletonRegion label="Loading participation summary…">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="mt-2 h-3 w-40 max-w-full" />
      </SkeletonRegion>
    );
  if (unavailable)
    return (
      <p className="text-xs text-muted-foreground">Participation unavailable</p>
    );
  if (!metrics || !metrics.expected || metrics.completion_rate == null)
    return (
      <div className="flex items-start gap-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          <ChartNoAxesColumn className="size-4" aria-hidden="true" />
        </span>
        <div className="min-w-0 space-y-1">
          <p className="text-xs font-medium">No participation data</p>
          <p className="text-xs text-muted-foreground">
            Stats appear after scheduled check-ins.
          </p>
        </div>
      </div>
    );
  const rate = metrics.completion_rate;
  const tone =
    rate >= 75
      ? 'text-success'
      : rate >= 40
        ? 'text-warning'
        : 'text-destructive';
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className={cn('text-lg font-semibold tabular-nums', tone)}>
          {rate}%
        </span>
        <span className={cn('text-xs font-medium', tone)}>
          {healthLabel(rate)}
        </span>
        <ParticipationSparkline
          series={metrics.series ?? []}
          tone={rate >= 75 ? 'success' : rate >= 40 ? 'warning' : 'destructive'}
        />
      </div>
      <p className="text-xs text-muted-foreground">
        {metrics.completed} of {metrics.expected} filed · last 14 days
      </p>
    </div>
  );
}

export function StandupRow({
  standup,
  channel,
  metrics,
  healthPending,
  healthUnavailable,
  editable,
  onEdit,
}: {
  standup: Standup;
  channel?: string;
  metrics?: ScheduleParticipation;
  healthPending: boolean;
  healthUnavailable: boolean;
  editable: boolean;
  onEdit: () => void;
}) {
  const { save, remove } = useStandupMutations();
  const [deleting, setDeleting] = useState(false);
  const menuTrigger = useRef<HTMLButtonElement>(null);
  const busy = save.isPending || remove.isPending;
  const nextRun = standup.active
    ? nextRunLabel(standup.next_run, standup.schedule_tz)
    : null;

  return (
    <li className="p-4 sm:p-5">
      <div className="grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)_minmax(0,1fr)_auto] lg:items-center lg:gap-5">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="min-w-0 break-words font-semibold">
              {standup.name}
            </h2>
            <Badge
              variant="secondary"
              className={
                standup.active ? 'bg-success/10 text-success' : undefined
              }
            >
              <span
                className={cn(
                  'size-1.5 rounded-full',
                  standup.active ? 'bg-success' : 'bg-muted-foreground',
                )}
              />
              {standup.active ? 'Active' : 'Paused'}
            </Badge>
          </div>
          <p className="break-all text-sm text-muted-foreground">
            #{channel ?? standup.channel_id}
          </p>
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Users className="size-3.5 shrink-0" aria-hidden="true" />
            {standup.participants?.length
              ? `${standup.participants.length} participant${standup.participants.length === 1 ? '' : 's'}`
              : 'Everyone in the channel'}
          </p>
        </div>
        <div className="min-w-0 space-y-1.5">
          <p className="flex items-center gap-1.5 text-sm font-medium">
            <Clock3
              className="size-3.5 text-muted-foreground"
              aria-hidden="true"
            />
            <span className="tabular-nums">{standup.schedule_time}</span>
            <span className="text-xs font-normal text-muted-foreground">
              {scheduleDays(standup.schedule_days)}
            </span>
          </p>
          <p className="break-words text-xs text-muted-foreground">
            {standup.schedule_tz}
          </p>
          {nextRun && !standup.registration_error && (
            <p className="text-xs text-muted-foreground">Next: {nextRun}</p>
          )}
          {!standup.active && (
            <p className="text-xs text-muted-foreground">Schedule paused</p>
          )}
        </div>
        <Participation
          metrics={metrics}
          pending={healthPending}
          unavailable={healthUnavailable}
        />
        {editable && (
          <div className="flex items-center gap-1 sm:justify-end">
            <Button
              size="sm"
              className="h-8"
              variant="outline"
              disabled={busy}
              onClick={onEdit}
              aria-label={`Edit ${standup.name}`}
            >
              Edit
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger
                ref={menuTrigger}
                render={
                  <Button size="icon-sm" variant="ghost" className="size-8" />
                }
                aria-label={`Actions for ${standup.name}`}
                disabled={busy}
              >
                <MoreHorizontal />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-40">
                <DropdownMenuItem
                  disabled={busy}
                  onClick={() =>
                    save.mutate(
                      { id: standup.id, body: { active: !standup.active } },
                      { onError: (error) => toast.error(errorMessage(error)) },
                    )
                  }
                >
                  {standup.active ? <Pause /> : <Play />}
                  {standup.active ? 'Pause' : 'Resume'}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  variant="destructive"
                  disabled={busy}
                  onClick={() => {
                    remove.reset();
                    setDeleting(true);
                  }}
                >
                  <Trash />
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}
      </div>
      {standup.registration_error && (
        <p
          role="alert"
          className="mt-4 flex items-start gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            <strong>This standup never runs.</strong>{' '}
            {standup.registration_error}
          </span>
        </p>
      )}
      <AlertDialog
        open={deleting}
        onOpenChange={(open) => {
          if (!remove.isPending) setDeleting(open);
        }}
      >
        <AlertDialogContent finalFocus={menuTrigger}>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {standup.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              This standup will be deleted. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {remove.error && (
            <p role="alert" className="text-sm text-destructive">
              {errorMessage(remove.error)}
            </p>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(standup.id, {
                  onSuccess: () => {
                    setDeleting(false);
                    toast.success('Standup deleted');
                  },
                })
              }
            >
              {remove.isPending ? 'Deleting…' : 'Delete standup'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </li>
  );
}
