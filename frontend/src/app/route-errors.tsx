import { Link, useRouteError } from 'react-router';

import { ErrorState } from '@/common/components/page';

export function RouteError() {
  const error = useRouteError();

  return (
    <div className="page">
      <ErrorState error={error} retry={() => window.location.reload()} />
    </div>
  );
}

export function NotFound() {
  return (
    <div className="page text-center">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="mt-2 text-muted-foreground">This page does not exist.</p>
      <Link
        className="mt-5 inline-block text-primary underline"
        to="/dashboard/standups"
      >
        Return to your workspace
      </Link>
    </div>
  );
}
