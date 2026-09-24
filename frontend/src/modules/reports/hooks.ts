import { useQuery } from '@tanstack/react-query';

import type { Api } from '@/common/api/client';
import type {
  ExportCsvParams,
  GetReportsParams,
} from '@/common/api/generated/data-contracts';
import { useServices } from '@/common/api/services-context';
import { useMemberDirectory } from '@/common/api/use-member-directory';
import { useSession } from '@/common/auth/use-session';

import { reportsOptions } from './queries';

export function useReports(filters: GetReportsParams, enabled = true) {
  const { data: session } = useSession();

  const reports = useQuery({
    ...reportsOptions(useServices(), session?.team_id, filters),
    enabled: !!session && enabled,
  });
  const members = useMemberDirectory();

  return { reports, members };
}

export async function exportReports(api: Api, filters: ExportCsvParams) {
  return (await api.reports.exportCsv(filters, { format: 'blob' })).data;
}
