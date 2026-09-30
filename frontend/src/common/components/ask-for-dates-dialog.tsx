import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { errorMessage } from '@/common/api/errors';
import { channelsOptions } from '@/common/api/queries';
import { queryKeys } from '@/common/api/query-keys';
import { useServices } from '@/common/api/services-context';
import { useSession } from '@/common/auth/use-session';
import { Button } from '@/common/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/common/components/ui/dialog';

const people = (count: number) =>
  `${count} ${count === 1 ? 'person' : 'people'}`;

function useAskForDates(open: boolean) {
  const services = useServices();
  const { api } = services;
  const { data: session } = useSession();
  const team = session?.team_id;
  const client = useQueryClient();
  const key = queryKeys.feature(team, 'celebrations', 'ask-dates');

  const preview = useQuery({
    queryKey: key,
    queryFn: async ({ signal }) =>
      (await api.celebrations.previewAskForDates({ signal })).data,
    enabled: !!team && open,
  });
  const channels = useQuery(channelsOptions(services, team));

  const send = useMutation({
    mutationFn: () => api.celebrations.askForDates(),
    onSuccess: () => client.invalidateQueries({ queryKey: key }),
  });

  return { preview, send, channels };
}

/**
 * Preview who would be asked for their dates, and the DM they would get,
 * before sending. Used from Celebrations and from Members.
 */
export function AskForDatesDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { preview, send, channels } = useAskForDates(open);
  const count = preview.data?.count ?? 0;
  // The DM mentions the channel; show it the way Slack will.
  const message = (preview.data?.message ?? '').replace(
    /<#([A-Z0-9_]+)>/,
    (_mention, id: string) =>
      `#${channels.data?.find((channel) => channel.id === id)?.name ?? 'channel'}`,
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Ask for birthdays and start dates</DialogTitle>
          <DialogDescription>
            Morgenruf sends a direct message to everyone who has neither date on
            file. Nobody is asked more than once in 30 days, and anyone who
            chose not to be celebrated is left out.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          {preview.isPending ? (
            <p role="status" className="text-sm text-muted-foreground">
              Counting people…
            </p>
          ) : preview.isError ? (
            <p role="alert" className="text-sm text-destructive">
              {errorMessage(preview.error)}
            </p>
          ) : (
            <>
              <p className="text-sm font-medium">
                {count
                  ? `${people(count)} will be asked.`
                  : 'Everyone has been asked recently or already has dates on file.'}
              </p>
              {!preview.data?.ready && (
                <p className="text-sm text-muted-foreground">
                  Choose a channel and a timezone for Celebrations first. The
                  message names the channel.
                </p>
              )}
              <div
                aria-label="Message preview"
                className="space-y-2 rounded-lg border bg-muted/30 p-4 text-sm"
              >
                <p className="whitespace-pre-wrap">{message}</p>
                <div className="flex flex-wrap gap-2">
                  <span className="rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground">
                    Add my dates
                  </span>
                  <span className="rounded-md border px-2 py-1 text-xs font-medium">
                    Skip me
                  </span>
                </div>
              </div>
            </>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={
              !count ||
              !preview.data?.ready ||
              send.isPending ||
              preview.isPending
            }
            onClick={() =>
              send.mutate(undefined, {
                onSuccess: ({ data }) => {
                  toast.success(`Asking ${people(data.count)} for their dates`);
                  onOpenChange(false);
                },
              })
            }
          >
            {send.isPending ? 'Sending…' : `Ask ${people(count)}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
