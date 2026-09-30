/** What each Slack permission lets Morgenruf do, in words a person can act on. */
const scopeWords: Record<string, string> = {
  'mpim:write': 'start group messages',
  'mpim:history': 'read replies in those group messages',
  'users.profile:read': 'read member profiles',
  'users:read': 'see who is in the workspace',
  'reactions:write': 'add emoji reactions',
  'channels:read': 'list channels',
  'groups:write': 'manage private channels',
  'chat:write': 'post messages',
  'im:write': 'send direct messages',
};

/** "start group messages and read member profiles" for a list of scopes. */
export function describeScopes(scopes: readonly string[]): string {
  const words = [
    ...new Set(
      scopes.map(
        (scope) => scopeWords[scope] ?? 'use another Slack permission',
      ),
    ),
  ];

  if (words.length < 2) return words[0] ?? '';

  return `${words.slice(0, -1).join(', ')} and ${words.at(-1)}`;
}
