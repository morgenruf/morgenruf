import type { ComponentType } from 'react';

export type DashboardRouteMetadata = {
  title: string;
  Skeleton: ComponentType;
  module?: string;
  requireActive?: boolean;
  customGate?: boolean;
  administration?: string;
};

declare module '@tanstack/react-router' {
  interface StaticDataRouteOption {
    workspace?: DashboardRouteMetadata;
  }
}
