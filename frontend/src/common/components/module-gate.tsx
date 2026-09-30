import type { ReactNode } from 'react';
import { Link } from '@tanstack/react-router';

import { useWorkspaceModules } from '@/common/api/use-workspace-modules';
import { usePermissions } from '@/common/auth/use-session';
import { describeScopes } from '@/common/lib/slack-scopes';

import { EmptyState, ErrorState } from './page';
import { Button } from './ui/button';

export function ModuleGate({
  module,
  label,
  children,
  requireActive = true,
  loadingFallback,
}: {
  module: string;
  label: string;
  children: ReactNode;
  requireActive?: boolean;
  loadingFallback: ReactNode;
}) {
  const query = useWorkspaceModules();
  const { isAdmin } = usePermissions();

  if (query.isPending) return loadingFallback;

  if (query.error)
    return (
      <div className="page">
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      </div>
    );

  const feature = query.data?.find((feature) => feature.name === module);

  if (!feature || !feature.available)
    return (
      <div className="page">
        <EmptyState
          title={`${label} unavailable`}
          description="This feature is not included in this deployment. Contact your administrator for access."
        />
      </div>
    );

  if (requireActive && feature.missing_scopes.length)
    return (
      <div className="page">
        <EmptyState
          title={`${label} need more Slack access`}
          description={
            <>
              <span className="block">
                Morgenruf needs permission to{' '}
                {describeScopes(feature.missing_scopes)}. Slack asks for it when
                the app is authorised again.
              </span>
              <span className="mt-2 block">
                {isAdmin
                  ? 'Choose Re-authorise Slack and approve the request. Nothing else changes.'
                  : 'Ask a workspace administrator to reconnect Slack.'}
              </span>
            </>
          }
          action={
            isAdmin && (
              <Button render={<a href="/install" />}>Re-authorise Slack</Button>
            )
          }
        />
      </div>
    );

  if (requireActive && !feature.active)
    return (
      <div className="page">
        <EmptyState
          title={`${label} switched off`}
          description={
            isAdmin
              ? 'Enable this feature in workspace settings to get started.'
              : 'Ask a workspace administrator to enable this feature.'
          }
          action={
            isAdmin && (
              <Button
                nativeButton={false}
                role="link"
                render={<Link to="/dashboard/settings" />}
              >
                Open workspace settings
              </Button>
            )
          }
        />
      </div>
    );

  return children;
}
