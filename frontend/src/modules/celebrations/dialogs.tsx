import { useId, useState } from 'react';
import { toast } from 'sonner';

import { errorMessage } from '@/common/api/errors';
import type {
  HolidayImportInput,
  HolidayImportResult,
} from '@/common/api/generated/data-contracts';
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
import { formatDate } from '@/common/lib/format';

const example = `date,name
2026-12-25,Christmas Day
2027-01-01,New Year's Day`;

export function ImportHolidaysDialog({
  open,
  onOpenChange,
  run,
  pending,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  run: (input: HolidayImportInput) => Promise<{ data: HolidayImportResult }>;
  pending: boolean;
}) {
  const id = useId();
  const [csv, setCsv] = useState('');
  const [preview, setPreview] = useState<HolidayImportResult | null>(null);
  const [error, setError] = useState('');

  function reset() {
    setCsv('');
    setPreview(null);
    setError('');
  }

  async function submit(write: boolean) {
    setError('');

    try {
      const { data } = await run({ csv, preview: !write });

      if (write) {
        toast.success(
          `Saved ${data.written} holiday${data.written === 1 ? '' : 's'}`,
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
          <DialogTitle>Import holidays</DialogTitle>
          <DialogDescription>
            Paste or upload a CSV with the columns <code>date,name</code>, one
            holiday per line, dates as YYYY-MM-DD. A date already on the list
            takes the new name. Nothing is saved until you have checked the
            preview.
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

          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}

          {preview && (
            <section aria-label="Import preview" className="space-y-3">
              <p className="text-sm">
                {preview.ready} to save · {preview.invalid} invalid
              </p>
              <ScrollArea
                className="max-h-64 rounded-lg border"
                viewportProps={{
                  role: 'region',
                  'aria-label': 'Holidays in the file',
                }}
              >
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Line</TableHead>
                      <TableHead>Date</TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>Result</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {preview.rows.map((row) => (
                      <TableRow key={row.line}>
                        <TableCell>{row.line}</TableCell>
                        <TableCell>
                          {row.date ? formatDate(row.date) : 'Not a date'}
                        </TableCell>
                        <TableCell className="break-all">{row.name}</TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              row.status === 'ready' ? 'default' : 'destructive'
                            }
                          >
                            {row.status === 'ready'
                              ? 'Will be saved'
                              : 'Invalid'}
                          </Badge>
                          {row.error && (
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
              : `Save ${preview?.ready ?? 0} holiday${preview?.ready === 1 ? '' : 's'}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
