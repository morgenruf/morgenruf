import { useEffect, useState } from 'react';
import { DownloadIcon, FileTextIcon, UploadIcon } from 'lucide-react';

import { Textarea } from '@/common/components/ui/textarea';
import { downloadText } from '@/common/lib/csv';
import { cn } from '@/common/lib/utils';

/**
 * Paste a CSV, drop a file on it, or browse for one. The example doubles as a
 * template the person can download and fill in.
 */
export function CsvInput({
  id,
  value,
  onChange,
  example,
  templateName,
}: {
  id: string;
  value: string;
  onChange: (text: string) => void;
  example: string;
  templateName: string;
}) {
  const [fileName, setFileName] = useState('');
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    if (!value) setFileName('');
  }, [value]);

  async function read(file: File | undefined) {
    if (!file) return;
    setFileName(file.name);
    onChange(await file.text());
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm font-medium">
        <label htmlFor={`${id}-csv`}>CSV</label>
        <button
          type="button"
          className="inline-flex items-center gap-1 text-xs font-normal text-primary underline-offset-4 hover:underline"
          onClick={() => downloadText(templateName, `${example}\n`)}
        >
          <DownloadIcon className="size-3.5" aria-hidden />
          Download template
        </button>
      </div>
      <Textarea
        id={`${id}-csv`}
        className="min-h-28 font-mono placeholder:text-muted-foreground/50"
        placeholder={example}
        value={value}
        onChange={(event) => {
          setFileName('');
          onChange(event.target.value);
        }}
      />
      <label
        htmlFor={`${id}-file`}
        className={cn(
          'flex cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed px-3 py-4 text-sm text-muted-foreground transition-colors hover:border-ring hover:text-foreground',
          dragging && 'border-ring bg-muted/50 text-foreground',
        )}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          void read(event.dataTransfer.files?.[0]);
        }}
      >
        {fileName ? (
          <>
            <FileTextIcon className="size-4" aria-hidden />
            <span className="text-foreground">{fileName}</span>
            <span>· choose another</span>
          </>
        ) : (
          <>
            <UploadIcon className="size-4" aria-hidden />
            <span>
              Drop a CSV file here, or{' '}
              <span className="text-primary underline">browse</span>
            </span>
          </>
        )}
        <input
          id={`${id}-file`}
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          onChange={(event) => {
            void read(event.target.files?.[0]);
            event.target.value = '';
          }}
        />
      </label>
    </div>
  );
}
