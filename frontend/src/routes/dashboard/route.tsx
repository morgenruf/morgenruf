import { createFileRoute, Outlet } from '@tanstack/react-router';

/** Login shares the URL prefix, but never enters the authenticated layout. */
export const Route = createFileRoute('/dashboard')({ component: Outlet });
