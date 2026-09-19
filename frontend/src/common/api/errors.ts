export function errorMessage(
  error: unknown,
  fallback = 'Something went wrong. Please try again.',
): string {
  if (error && typeof error === 'object') {
    if ('error' in error && error.error && typeof error.error === 'object') {
      const body = error.error as { error?: unknown; message?: unknown };

      if (typeof body.error === 'string') return body.error;
      if (typeof body.message === 'string') return body.message;
    }

    if ('status' in error && error.status === 403)
      return 'You do not have permission to perform this action.';

    if ('status' in error && error.status === 401)
      return 'Your session has expired. Please sign in again.';
  }

  if (error instanceof TypeError)
    return 'Could not reach the server. Check your connection and try again.';

  if (error instanceof Error && error.message) return error.message;

  return fallback;
}
