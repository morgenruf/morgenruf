import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { useSession } from '@/common/auth/use-session';

import { memberDirectoryOptions } from './queries';
import { useServices } from './services-context';

/** Share the member directory without making person identities block page content. */
export function useMemberDirectory({
  channel,
  enabled = true,
}: {
  channel?: string;
  enabled?: boolean;
} = {}) {
  const { data: session } = useSession();
  const team = session?.team_id;

  const query = useQuery({
    ...memberDirectoryOptions(useServices(), team, channel),
    enabled: !!team && enabled,
  });
  const membersById = useMemo(
    () => new Map(query.data?.map((member) => [member.id, member])),
    [query.data],
  );

  function person(userId: string, fallbackName?: string | null) {
    const member = membersById.get(userId);

    return {
      name:
        member?.name?.trim() ||
        member?.display_name?.trim() ||
        fallbackName?.trim() ||
        userId,
      avatar: member?.avatar,
    };
  }

  return { ...query, person };
}
