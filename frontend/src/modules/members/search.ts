import { z } from 'zod';

export const validateSearch = z.object({
  channel: z.string().catch('').default(''),
  q: z.string().catch('').default(''),
  role: z.enum(['', 'admin', 'member']).catch('').default(''),
  tracking: z.enum(['', 'tracked', 'untracked']).catch('').default(''),
  sort: z.enum(['', 'name', 'role', 'timezone']).catch('').default(''),
});

export type Search = z.output<typeof validateSearch>;
