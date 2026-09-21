import type { ReactNode } from 'react';
import { AlertCircle, Inbox, type LucideIcon } from 'lucide-react';

import { errorMessage } from '@/common/api/errors';
import { cn } from '@/common/lib/utils';

import { Button } from './ui/button';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';

export function PageHeader({
  title,
  description,
  actions,
  reserveActionSpace = false,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  reserveActionSpace?: boolean;
}) {
  return (
    <header
      className={cn(
        'flex items-center justify-between gap-4',
        reserveActionSpace && 'min-h-9',
      )}
    >
      <h1 className="min-w-0 break-words text-xl font-semibold tracking-tight">
        {title}
      </h1>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {actions}
        </div>
      ) : description ? (
        <div className="min-w-0 text-right text-sm text-muted-foreground">
          {description}
        </div>
      ) : null}
    </header>
  );
}

export function ErrorState({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-destructive/30 bg-destructive/5 p-6"
    >
      <div className="flex items-center gap-2 font-medium">
        <AlertCircle className="size-4 text-destructive" />
        Could not load this view
      </div>
      <p className="mt-2 text-sm text-muted-foreground">
        {errorMessage(error)}
      </p>
      {retry && (
        <Button variant="outline" className="mt-4" onClick={retry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed px-6 py-12 text-center">
      <Inbox className="mb-3 size-6 text-muted-foreground" />
      <h2 className="font-medium">{title}</h2>
      {description && (
        <div className="mt-1 max-w-md text-sm text-muted-foreground">
          {description}
        </div>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function StatCard({
  label,
  value,
  description,
  icon: Icon,
  tone = 'primary',
}: {
  label: string;
  value: ReactNode;
  description?: ReactNode;
  icon?: LucideIcon;
  tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'destructive';
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle className="text-baes font-medium text-muted-foreground">
          {label}
        </CardTitle>
        {Icon && (
          <span
            className={cn(
              'grid size-8 shrink-0 place-items-center rounded-lg',
              {
                'bg-muted text-muted-foreground': tone === 'neutral',
                'bg-primary/10 text-primary': tone === 'primary',
                'bg-success/10 text-success': tone === 'success',
                'bg-warning/10 text-warning': tone === 'warning',
                'bg-destructive/10 text-destructive': tone === 'destructive',
              },
            )}
          >
            <Icon className="size-4" aria-hidden="true" />
          </span>
        )}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
        {description && (
          <div className="mt-1 text-xs text-muted-foreground">
            {description}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
