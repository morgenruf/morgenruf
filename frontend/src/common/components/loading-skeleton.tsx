import { createContext, useContext, type ReactNode } from 'react';

import { LoadingTransition } from '@/common/components/loading-transition';
import { cn } from '@/common/lib/utils';

import { PageHeader } from './page';
import { Card, CardContent, CardHeader } from './ui/card';
import { Skeleton } from './ui/skeleton';

const LoadingContext = createContext(false);

/** Announce each independently loading region once, even when compositions nest. */
export function SkeletonRegion({
  label,
  children,
  className,
  contentClassName,
}: {
  label: string;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
}) {
  const nested = useContext(LoadingContext);

  if (nested) return <div className={className}>{children}</div>;

  return (
    <div aria-busy="true" className={className} data-loading-skeleton="">
      <span role="status" aria-label={label} className="sr-only">
        {label}
      </span>
      <div aria-hidden="true" className={contentClassName}>
        <LoadingContext.Provider value={true}>
          {children}
        </LoadingContext.Provider>
      </div>
    </div>
  );
}

export function SkeletonPage({
  title,
  children,
  className,
}: {
  title: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn('page', className)}>
      <PageHeader
        title={title}
        description={<Skeleton className="h-4 w-72 max-w-full" />}
      />
      <SkeletonRegion label={`Loading ${title.toLowerCase()}…`}>
        {children}
      </SkeletonRegion>
    </div>
  );
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton
          key={index}
          className={cn('h-3', index === lines - 1 ? 'w-2/3' : 'w-full')}
        />
      ))}
    </div>
  );
}

export function SkeletonCard({
  children,
  className,
}: {
  children?: ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader className="gap-2">
        <Skeleton className="h-4 w-40 max-w-full" />
        <Skeleton className="h-3 w-56 max-w-full" />
      </CardHeader>
      <CardContent>{children ?? <SkeletonText />}</CardContent>
    </Card>
  );
}

export function SkeletonStats({
  count = 4,
  className,
  icons = false,
}: {
  count?: number;
  className?: string;
  icons?: boolean;
}) {
  return (
    <div className={cn('grid gap-4 sm:grid-cols-2 lg:grid-cols-4', className)}>
      {Array.from({ length: count }, (_, index) => (
        <Card key={index}>
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <Skeleton className="h-3 w-24" />
            {icons && <Skeleton className="size-8 shrink-0 rounded-lg" />}
          </CardHeader>
          <CardContent className="space-y-2">
            <Skeleton className="h-8 w-20" />
            <Skeleton className="h-3 w-36 max-w-full" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export function SkeletonPeople({ rows = 4 }: { rows?: number }) {
  return (
    <div className="divide-y">
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          className="flex items-center gap-3 py-3 first:pt-0 last:pb-0"
        >
          <Skeleton className="size-9 shrink-0 rounded-full" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-4 w-32 max-w-full" />
            <Skeleton className="h-3 w-48 max-w-full" />
          </div>
          <Skeleton className="h-5 w-12 shrink-0" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonTable({
  columns = 4,
  rows = 5,
}: {
  columns?: number;
  rows?: number;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-96">
        <thead>
          <tr>
            {Array.from({ length: columns }, (_, index) => (
              <th key={index} className="border-b p-3">
                <Skeleton className="h-3 w-16 max-w-full" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, row) => (
            <tr key={row} className="border-b last:border-0">
              {Array.from({ length: columns }, (_, col) => (
                <td key={col} className="p-3">
                  <Skeleton
                    className={cn('h-4', col === 0 ? 'w-28' : 'w-16')}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SkeletonFields({
  count = 4,
  className,
}: {
  count?: number;
  className?: string;
}) {
  return (
    <div className={cn('form-grid', className)}>
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="space-y-2">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-9 w-full" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }, (_, index) => (
        <Card key={index}>
          <CardContent className="flex flex-col gap-4 p-5 sm:flex-row">
            <Skeleton className="size-10 shrink-0" />
            <div className="min-w-0 flex-1 space-y-3">
              <div className="flex gap-3">
                <Skeleton className="h-5 w-40 max-w-full" />
                <Skeleton className="h-5 w-14 shrink-0 rounded-full" />
              </div>
              <Skeleton className="h-4 w-56 max-w-full" />
              <SkeletonText lines={2} />
            </div>
            <div className="flex shrink-0 gap-2">
              <Skeleton className="h-8 w-16" />
              <Skeleton className="h-8 w-16" />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export function SkeletonChart({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'flex h-64 items-end gap-3 border-b border-l p-4',
        className,
      )}
    >
      {['h-2/5', 'h-3/5', 'h-1/2', 'h-4/5', 'h-3/5', 'h-full', 'h-4/5'].map(
        (height, index) => (
          <Skeleton
            key={index}
            className={cn('min-w-0 flex-1 rounded-b-none', height)}
          />
        ),
      )}
    </div>
  );
}

export function FieldSkeleton({
  label,
  className,
}: {
  label: string;
  className?: string;
}) {
  return (
    <SkeletonRegion label={label} className={className}>
      <Skeleton className="h-9 w-full" />
    </SkeletonRegion>
  );
}

/** Keep query-backed fields from presenting an empty option list while loading. */
export function LoadingField({
  pending,
  label,
  children,
  className,
  fieldLabel,
}: {
  pending: boolean;
  fieldLabel?: string;
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <LoadingTransition pending={pending} className={className}>
      {pending ? (
        <div className="space-y-2">
          {fieldLabel && (
            <div className="text-sm font-medium">{fieldLabel}</div>
          )}
          <FieldSkeleton label={label} />
        </div>
      ) : (
        children
      )}
    </LoadingTransition>
  );
}

export function SkeletonResponse() {
  return (
    <div className="grid gap-5 sm:grid-cols-2">
      {Array.from({ length: 3 }, (_, index) => (
        <div
          key={index}
          className={cn('space-y-3', index === 2 && 'sm:col-span-2')}
        >
          <Skeleton className="h-3 w-20" />
          <SkeletonText lines={index === 2 ? 2 : 3} />
        </div>
      ))}
    </div>
  );
}
