const legacySections = new Set([
  'today',
  'standups',
  'connect',
  'kudos',
  'members',
  'insights',
  'reports',
  'analytics',
  'settings',
  'automation',
  'webhooks',
  'mcp',
]);

export function legacyDashboardPath(hash: string) {
  const section = hash.replace(/^#/, '').split('?')[0];

  return legacySections.has(section)
    ? `/dashboard/${section}`
    : '/dashboard/standups';
}

export function isLegacyDashboardHash(hash: string) {
  return legacySections.has(hash.replace(/^#/, ''));
}
