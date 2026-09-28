import { useId, useState } from 'react';
import { toast } from 'sonner';

import { errorMessage } from '@/common/api/errors';
import type {
  MemberProfile,
  MemberProfileRecord,
  ProfileImportResult,
} from '@/common/api/generated/data-contracts';
import { ProfileForm } from '@/common/components/profile-form';
import { Badge } from '@/common/components/ui/badge';
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
import { ScrollArea } from '@/common/components/ui/scroll-area';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/common/components/ui/table';
import { Textarea } from '@/common/components/ui/textarea';
import { birthdayLabel } from '@/common/lib/profile';

export function EditProfileDialog({
  member,
  profile,
  pending,
  onSave,
  onClose,
}: {
  member: { id: string; name: string } | null;
  profile: MemberProfileRecord | undefined;
  pending: boolean;
  onSave: (id: string, data: MemberProfile) => Promise<unknown>;
  onClose: () => void;
}) {
  return (
    <Dialog open={!!member} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{member?.name}’s profile</DialogTitle>
          <DialogDescription>
            {profile && !profile.set_by_admin && profile.updated_by
              ? 'They filled this in themselves. Change it only if they asked you to.'
              : 'They can see and correct anything you enter here.'}
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          {member && (
            <ProfileForm
              profile={profile}
              pending={pending}
              onSave={(data) =>
                onSave(member.id, data).then(() => {
                  toast.success('Profile saved');
                  onClose();
                })
              }
              secondaryAction={
                <Button type="button" variant="outline" onClick={onClose}>
                  Cancel
                </Button>
              }
            />
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

const statusLabels: Record<string, string> = {
  ready: 'Will be saved',
  unchanged: 'Already on file',
  kept: 'Kept, set by the member',
  unmatched: 'No member with this email',
  invalid: 'Invalid',
};

const example = `email,birthday,start_date
priya@example.com,03-14,2023-03-01
tom@example.com,1990-07-04,2021-09-13`;

export function ImportDatesDialog({
  open,
  onOpenChange,
  run,
  pending,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  run: (input: {
    csv: string;
    preview: boolean;
    overwrite: boolean;
  }) => Promise<{ data: ProfileImportResult }>;
  pending: boolean;
}) {
  const id = useId();
  const [csv, setCsv] = useState('');
  const [overwrite, setOverwrite] = useState(false);
  const [preview, setPreview] = useState<ProfileImportResult | null>(null);
  const [error, setError] = useState('');

  function reset() {
    setCsv('');
    setOverwrite(false);
    setPreview(null);
    setError('');
  }

  async function submit(write: boolean) {
    setError('');

    try {
      const { data } = await run({ csv, preview: !write, overwrite });

      if (write) {
        toast.success(
          `Saved dates for ${data.written} member${data.written === 1 ? '' : 's'}`,
        );
        reset();
        onOpenChange(false);
      } else setPreview(data);
    } catch (failure) {
      setError(errorMessage(failure));
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import birthdays and start dates</DialogTitle>
          <DialogDescription>
            Paste or upload a CSV with the columns{' '}
            <code>email,birthday,start_date</code>. Birthdays can be MM-DD or a
            full date; the year is dropped and never stored. Nothing is saved
            until you have checked the preview.
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <div className="flex flex-col gap-2 text-sm font-medium">
            <label htmlFor={`${id}-csv`}>CSV</label>
            <Textarea
              id={`${id}-csv`}
              className="min-h-32 font-mono"
              placeholder={example}
              value={csv}
              onChange={(event) => {
                setCsv(event.target.value);
                setPreview(null);
              }}
            />
          </div>
          <div className="flex flex-col gap-2 text-sm font-medium">
            <label htmlFor={`${id}-file`}>Or choose a file</label>
            <input
              id={`${id}-file`}
              type="file"
              accept=".csv,text/csv"
              className="text-sm font-normal"
              onChange={async (event) => {
                const file = event.target.files?.[0];

                if (file) {
                  setCsv(await file.text());
                  setPreview(null);
                }
              }}
            />
          </div>
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={overwrite}
              onChange={(event) => {
                setOverwrite(event.target.checked);
                setPreview(null);
              }}
            />
            <span>
              Overwrite entries members made themselves. Leave this off to keep
              what people typed in over what the file says.
            </span>
          </label>

          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}

          {preview && (
            <section aria-label="Import preview" className="space-y-3">
              <p className="text-sm">
                {preview.ready} to save · {preview.unchanged} already on file ·{' '}
                {preview.kept} kept · {preview.unmatched} unmatched ·{' '}
                {preview.invalid} invalid
              </p>
              {preview.rows.length > 0 && (
                <ScrollArea
                  className="max-h-64 rounded-lg border"
                  viewportProps={{
                    role: 'region',
                    'aria-label': 'Rows in the file',
                  }}
                >
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Line</TableHead>
                        <TableHead>Email</TableHead>
                        <TableHead>Birthday</TableHead>
                        <TableHead>Started</TableHead>
                        <TableHead>Result</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {preview.rows.map((row) => (
                        <TableRow key={row.line}>
                          <TableCell>{row.line}</TableCell>
                          <TableCell className="break-all">
                            {row.email}
                          </TableCell>
                          <TableCell>
                            {birthdayLabel(row.birth_month, row.birth_day) ||
                              'Not given'}
                          </TableCell>
                          <TableCell>{row.start_date ?? 'Not given'}</TableCell>
                          <TableCell>
                            <Badge
                              variant={
                                row.status === 'ready'
                                  ? 'default'
                                  : row.status === 'invalid' ||
                                      row.status === 'unmatched'
                                    ? 'destructive'
                                    : 'secondary'
                              }
                            >
                              {statusLabels[row.status] ?? row.status}
                            </Badge>
                            {row.error && row.status === 'invalid' && (
                              <p className="mt-1 text-xs text-muted-foreground">
                                {row.error}
                              </p>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </ScrollArea>
              )}
            </section>
          )}
        </DialogBody>

        <DialogFooter>
          <Button
            variant="outline"
            disabled={!csv.trim() || pending}
            onClick={() => void submit(false)}
          >
            {pending && !preview ? 'Checking…' : 'Preview'}
          </Button>
          <Button
            disabled={!preview?.ready || pending}
            onClick={() => void submit(true)}
          >
            {pending && preview
              ? 'Saving…'
              : `Save ${preview?.ready ?? 0} member${preview?.ready === 1 ? '' : 's'}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
