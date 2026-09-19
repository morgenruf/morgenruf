export const queryKeys = {
  session: ['session'] as const,
  workspace: (teamId: string | undefined) => ['workspace', teamId] as const,
  feature: (
    teamId: string | undefined,
    feature: string,
    ...params: unknown[]
  ) => ['workspace', teamId, feature, ...params] as const,
};
