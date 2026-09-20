import type { ReactNode } from 'react';
import { Link } from 'react-router';

import { useWorkspaceModules } from '@/common/api/use-workspace-modules';
import { usePermissions } from '@/common/auth/use-session';

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
                Your workspace has not granted all the Slack permissions this
                feature requires.
              </span>
              <span className="mt-2 block text-xs">
                Missing: {feature.missing_scopes.join(', ')}
              </span>
              {!isAdmin && (
                <span className="mt-2 block">
                  Ask a workspace administrator to reconnect Slack.
                </span>
              )}
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
              <Button render={<Link to="/dashboard/settings" />}>
                Open workspace settings
              </Button>
            )
          }
        />
      </div>
    );

  return children;
}
