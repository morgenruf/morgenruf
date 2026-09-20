import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { WorkspaceModule } from '@/common/api/generated/data-contracts';

import { ModuleGate } from './module-gate';

const state = vi.hoisted(() => ({
  modules: [] as WorkspaceModule[],
  isAdmin: true,
}));

vi.mock('@/common/api/use-workspace-modules', () => ({
  useWorkspaceModules: () => ({
    data: state.modules,
    isPending: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

vi.mock('@/common/auth/use-session', () => ({
  usePermissions: () => ({ isAdmin: state.isAdmin }),
}));

const renderGate = (requireActive = true) =>
  render(
    <MemoryRouter>
      <ModuleGate
        loadingFallback={<div role="status">Loading insights…</div>}
        module="insights"
        label="Insights"
        requireActive={requireActive}
      >
        <div>Protected feature</div>
      </ModuleGate>
    </MemoryRouter>,
  );

beforeEach(() => {
  state.isAdmin = true;
  state.modules = [
    {
      name: 'insights',
      active: true,
      enabled: true,
      available: true,
      delegable: false,
      missing_scopes: [],
      required_scopes: [],
      nav: [],
    },
  ];
});

describe('direct URL module gating', () => {
  it('does not mount feature children for unavailable deployments', () => {
    state.modules[0].available = false;

    renderGate();

    expect(screen.getByText('Insights unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Protected feature')).not.toBeInTheDocument();
  });

  it('offers settings to administrators for disabled modules', () => {
    state.modules[0].active = false;

    renderGate();

    expect(
      screen.getByRole('link', { name: 'Open workspace settings' }),
    ).toHaveAttribute('href', '/dashboard/settings');
  });

  it('offers re-authorisation only to workspace admins when Slack permissions are missing', () => {
    state.modules[0].missing_scopes = ['groups:write'];
    state.isAdmin = false;

    renderGate();

    expect(
      screen.getByText(/Ask a workspace administrator to reconnect Slack/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'Re-authorise Slack' }),
    ).not.toBeInTheDocument();
  });

  it('allows Today aggregation when Insights is disabled but deployed', () => {
    state.modules[0].active = false;

    renderGate(false);

    expect(screen.getByText('Protected feature')).toBeInTheDocument();
  });
});
