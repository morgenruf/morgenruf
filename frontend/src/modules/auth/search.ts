import { z } from 'zod';

export const validateSearch = z.object({
  error: z.string().catch('').default(''),
  next: z.string().catch('').default(''),
});

export type Search = z.output<typeof validateSearch>;
