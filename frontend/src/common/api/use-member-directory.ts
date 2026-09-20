import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { useSession } from '@/common/auth/use-session';

import { api } from './client';
import { queryKeys } from './query-keys';

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
    queryKey: queryKeys.feature(team, 'members', channel || ''),
    enabled: !!team && enabled,
    queryFn: async ({ signal }) =>
      (
        await api.members.listMembers(channel ? { channel_id: channel } : {}, {
          signal,
        })
      ).data,
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
