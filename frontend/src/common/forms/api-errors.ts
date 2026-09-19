import type { FieldValues, Path, UseFormSetError } from 'react-hook-form';

import { errorMessage } from '@/common/api/errors';

/** Map backend field validation into RHF without introducing a second request schema. */
export function applyApiErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
): boolean {
  if (
    error &&
    typeof error === 'object' &&
    'error' in error &&
    error.error &&
    typeof error.error === 'object' &&
    'details' in error.error
  ) {
    const details = error.error.details;

    if (details && typeof details === 'object') {
      let mapped = false;

      for (const [field, messages] of Object.entries(details)) {
        if (
          Array.isArray(messages) &&
          messages.every((message) => typeof message === 'string')
        ) {
          setError(field as Path<T>, {
            type: 'server',
            message: messages.join(' '),
          });
          mapped = true;
        }
      }

      if (mapped) return true;
    }
  }

  setError('root.server', { type: 'server', message: errorMessage(error) });

  return false;
}
