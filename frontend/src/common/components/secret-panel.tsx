import { Copy } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from './ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';

/** The caller owns this short-lived value and must clear it on dismissal. */
export function SecretPanel({
  title,
  value,
  onDismiss,
}: {
  title: string;
  value: string | null;
  onDismiss: () => void;
}) {
  return (
    <Dialog
      open={value !== null}
      onOpenChange={(open) => {
        if (!open) onDismiss();
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            Copy this secret now. After you close this dialog, it cannot be
            shown again.
          </DialogDescription>
        </DialogHeader>
        <code
          className="break-all rounded-md border bg-muted p-4 font-mono text-sm"
          data-testid="one-time-secret"
        >
          {value}
        </code>
        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            onClick={() => {
              if (value)
                void navigator.clipboard.writeText(value).then(
                  () => toast.success('Secret copied'),
                  () =>
                    toast.error(
                      'Could not copy. Select and copy the secret manually.',
                    ),
                );
            }}
          >
            <Copy /> Copy
          </Button>
          <Button onClick={onDismiss}>Done</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
