import { NO_VALUE } from '@/common/lib/format';

/** A visible "n/a" that a screen reader announces as words, not letters. */
export function EmptyValue({ label = 'No value' }: { label?: string }) {
  return (
    <span className="text-muted-foreground">
      <span aria-hidden="true">{NO_VALUE}</span>
      <span className="sr-only">{label}</span>
    </span>
  );
}
