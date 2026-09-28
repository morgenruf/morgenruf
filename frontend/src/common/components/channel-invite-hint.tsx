import { RefreshCw } from 'lucide-react';

import { Button } from '@/common/components/ui/button';
import { cn } from '@/common/lib/utils';

/**
 * What to do when a channel picker has nothing in it.
 *
 * `/dashboard/api/channels` lists only the channels the bot is a member of,
 * and a new install is in none, so every picker starts empty. Shared so the
 * wording stays the same on every page that picks a channel.
 */
export const CHANNEL_INVITE_HINT =
  'Invite @Morgenruf to a channel first: type /invite @Morgenruf in the channel, then refresh this list.';

type ChannelsQuery = {
  data?: readonly unknown[];
  isSuccess: boolean;
  isFetching: boolean;
  refetch: () => unknown;
};

export function ChannelInviteHint({
  channels,
  className,
}: {
  channels: ChannelsQuery;
  className?: string;
}) {
  if (!channels.isSuccess || (channels.data?.length ?? 0) > 0) return null;

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-x-3 gap-y-2 text-xs font-normal text-muted-foreground',
        className,
      )}
    >
      <p className="min-w-0 flex-1 basis-56">{CHANNEL_INVITE_HINT}</p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={channels.isFetching}
        onClick={() => void channels.refetch()}
      >
        <RefreshCw aria-hidden="true" /> Refresh channels
      </Button>
    </div>
  );
}
