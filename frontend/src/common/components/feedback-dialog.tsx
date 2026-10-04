import { useMutation } from '@tanstack/react-query';
import { Bug, Lightbulb, MessageCircle, type LucideIcon } from 'lucide-react';
import { useForm, useWatch } from 'react-hook-form';
import { toast } from 'sonner';

import type { FeedbackInput } from '@/common/api/generated/data-contracts';
import { useServices } from '@/common/api/services-context';
import { Button } from '@/common/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/common/components/ui/dialog';
import { Input } from '@/common/components/ui/input';
import { Label } from '@/common/components/ui/label';
import { Textarea } from '@/common/components/ui/textarea';
import { applyApiErrors } from '@/common/forms/api-errors';
import { cn } from '@/common/lib/utils';

type Kind = FeedbackInput['kind'];

const kinds: Array<{
  value: Kind;
  label: string;
  hint: string;
  icon: LucideIcon;
  placeholder: string;
}> = [
  {
    value: 'bug',
    label: 'Report a bug',
    hint: 'Something is broken',
    icon: Bug,
    placeholder: 'What did you do, what happened, and what did you expect?',
  },
  {
    value: 'idea',
    label: 'Suggest an improvement',
    hint: 'An idea to make it better',
    icon: Lightbulb,
    placeholder: 'What would you like Morgenruf to do, and why?',
  },
  {
    value: 'other',
    label: 'Something else',
    hint: 'Questions, praise, anything',
    icon: MessageCircle,
    placeholder: 'Tell us anything.',
  },
];

type Values = { kind: Kind; title: string; details: string };

const blank: Values = { kind: 'bug', title: '', details: '' };

/** Bug reports and ideas from anyone signed in, filed for the maintainer. */
export function FeedbackDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { api } = useServices();
  const form = useForm<Values>({ defaultValues: blank });
  const kind = useWatch({ control: form.control, name: 'kind' });
  const current = kinds.find((item) => item.value === kind) ?? kinds[0];

  const send = useMutation({
    mutationFn: (values: Values) =>
      api.session.sendFeedback({
        ...values,
        page: `${location.pathname}${location.search}`.slice(0, 300),
      }),
  });

  function close(next: boolean) {
    if (!next) form.reset(blank);
    onOpenChange(next);
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Send feedback</DialogTitle>
        </DialogHeader>
        <form
          className="flex min-h-0 flex-col gap-4"
          onSubmit={form.handleSubmit((values) =>
            send.mutate(values, {
              onSuccess: () => {
                toast.success('Thanks, your feedback was sent');
                close(false);
              },
              onError: (error) => applyApiErrors(error, form.setError),
            }),
          )}
        >
          <DialogBody className="space-y-4">
            <div
              role="radiogroup"
              aria-label="Kind of feedback"
              className="grid gap-2 sm:grid-cols-3"
            >
              {kinds.map((item) => {
                const selected = item.value === kind;

                return (
                  <button
                    key={item.value}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => form.setValue('kind', item.value)}
                    className={cn(
                      'flex flex-col items-start gap-1 rounded-lg border p-3 text-left transition-colors outline-none hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring/30',
                      selected &&
                        'border-primary bg-primary/5 ring-1 ring-primary',
                    )}
                  >
                    <item.icon
                      className={cn(
                        'size-5',
                        selected ? 'text-primary' : 'text-muted-foreground',
                      )}
                      aria-hidden="true"
                    />
                    <span className="text-sm font-medium">{item.label}</span>
                    <span className="text-xs text-muted-foreground">
                      {item.hint}
                    </span>
                  </button>
                );
              })}
            </div>
            <div className="space-y-2">
              <Label htmlFor="feedback-title">Title</Label>
              <Input
                id="feedback-title"
                placeholder="One line summary"
                maxLength={120}
                aria-invalid={!!form.formState.errors.title}
                {...form.register('title', {
                  required: 'Add a short title.',
                  minLength: { value: 3, message: 'Add a short title.' },
                })}
              />
              {form.formState.errors.title && (
                <p role="alert" className="text-sm text-destructive">
                  {form.formState.errors.title.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="feedback-details">Details</Label>
              <Textarea
                id="feedback-details"
                placeholder={current.placeholder}
                maxLength={5000}
                className="min-h-32"
                {...form.register('details')}
              />
              <p className="text-xs text-muted-foreground">
                Your workspace, the page you are on and your browser are added,
                so we can reproduce it and reply.
              </p>
            </div>
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
              onClick={() => close(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={send.isPending}>
              {send.isPending ? 'Sending…' : 'Send feedback'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
