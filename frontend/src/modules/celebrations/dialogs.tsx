import { useId, useRef, useState } from 'react';
import { toast } from 'sonner';

import { errorMessage } from '@/common/api/errors';
import type {
  HolidayImportInput,
  HolidayImportResult,
} from '@/common/api/generated/data-contracts';
import { CsvInput } from '@/common/components/csv-input';
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
import { useAutoPreview } from '@/common/lib/csv';
import { formatDate, plural } from '@/common/lib/format';

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
  const latest = useRef(0);

  function reset() {
    setCsv('');
    setPreview(null);
    setError('');
  }

  async function submit(write: boolean) {
    setError('');
    const request = ++latest.current;

    try {
      const { data } = await run({ csv, preview: !write });
      if (request !== latest.current) return;

      if (write) {
        toast.success(`Saved ${plural(data.written, 'holiday')}`);
        reset();
        onOpenChange(false);
      } else setPreview(data);
    } catch (failure) {
      if (request === latest.current) setError(errorMessage(failure));
    }
  }

  useAutoPreview(csv, [], () => void submit(false));

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
            Columns <code>date,name</code>, dates as{' '}
            <code className="whitespace-nowrap">YYYY-MM-DD</code>. You see a
            preview before anything is saved.
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <CsvInput
            id={id}
            value={csv}
            example={example}
            templateName="holidays-template.csv"
            onChange={(text) => {
              setCsv(text);
              setPreview(null);
            }}
          />

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
          {pending && !preview && (
            <p className="mr-auto text-sm text-muted-foreground">Checking…</p>
          )}
          {!!preview?.ready && (
            <Button disabled={pending} onClick={() => void submit(true)}>
              {pending ? 'Saving…' : `Save ${plural(preview.ready, 'holiday')}`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
