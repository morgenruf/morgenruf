import {
  SkeletonCard,
  SkeletonPage,
  SkeletonRegion,
  SkeletonTable,
  SkeletonText,
} from '@/common/components/loading-skeleton';

export function McpKeysSkeleton() {
  return (
    <SkeletonRegion label="Loading API keys…">
      <SkeletonTable columns={6} />
    </SkeletonRegion>
  );
}
export function McpPageSkeleton() {
  return (
    <SkeletonPage title="MCP">
      <div className="space-y-6">
        <SkeletonCard>
          <SkeletonText lines={5} />
        </SkeletonCard>
        <SkeletonCard>
          <McpKeysSkeleton />
        </SkeletonCard>
        <SkeletonCard>
          <SkeletonText lines={5} />
        </SkeletonCard>
      </div>
    </SkeletonPage>
  );
}
