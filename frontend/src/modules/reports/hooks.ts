import { useQuery } from '@tanstack/react-query';

import { api } from '@/common/api/client';
import type {
  ExportCsvParams,
  GetReportsParams,
} from '@/common/api/generated/data-contracts';
import { queryKeys } from '@/common/api/query-keys';
import { useSession } from '@/common/auth/use-session';

export function useReports(filters: GetReportsParams, enabled = true) {
  const { data: session } = useSession();

  const reports = useQuery({
    queryKey: queryKeys.feature(session?.team_id, 'reports', filters),
    queryFn: async ({ signal }) =>
      (await api.reports.getReports(filters, { signal })).data,
    enabled,
  });

  const members = useQuery({
    queryKey: queryKeys.feature(session?.team_id, 'members'),
    queryFn: async ({ signal }) =>
      (await api.members.listMembers({}, { signal })).data,
  });

  return { reports, members };
}

export async function exportReports(filters: ExportCsvParams) {
  return (await api.reports.exportCsv(filters, { format: 'blob' })).data;
}
