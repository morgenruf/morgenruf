import { useCallback, useRef, useState } from 'react';

import {
  ConfirmDialog,
  type ConfirmOptions,
} from '@/common/components/confirm-dialog';

/**
 * Ask first, then act: `if (await confirm({...})) doIt()`. Suits quick actions
 * whose failure is reported by the global mutation toast. Render `dialog`
 * once in the component.
 */
export function useConfirm() {
  // The options outlive `open` so the dialog keeps its text while closing.
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const [open, setOpen] = useState(false);
  const resolver = useRef<((value: boolean) => void) | null>(null);

  const settle = useCallback((value: boolean) => {
    resolver.current?.(value);
    resolver.current = null;
    setOpen(false);
  }, []);

  const confirm = useCallback((next: ConfirmOptions) => {
    resolver.current?.(false);
    setOptions(next);
    setOpen(true);
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve;
    });
  }, []);

  const dialog = (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) settle(false);
      }}
      title={options?.title ?? ''}
      description={options?.description}
      confirmLabel={options?.confirmLabel ?? 'Confirm'}
      cancelLabel={options?.cancelLabel}
      destructive={options?.destructive}
      onConfirm={() => settle(true)}
    />
  );

  return { confirm, dialog };
}
