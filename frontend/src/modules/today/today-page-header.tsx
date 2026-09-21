import type { ReactNode } from 'react';

import { PageHeader } from '@/common/components/page';

export function TodayPageHeader({ description }: { description: ReactNode }) {
  const hour = new Date().getHours();

  return (
    <PageHeader
      title={
        hour < 12
          ? 'Good morning'
          : hour < 18
            ? 'Good afternoon'
            : 'Good evening'
      }
      description={description}
    />
  );
}
