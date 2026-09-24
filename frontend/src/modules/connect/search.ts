import { z } from 'zod';

export const validateSearch = z.object({
  program: z.string().regex(/^\d+$/).catch('').default(''),
});

export type Search = z.output<typeof validateSearch>;
