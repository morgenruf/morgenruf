import { z } from 'zod';

export const validateSearch = z.object({
  q: z.string().catch('').default(''),
  status: z.enum(['', 'active', 'paused']).catch('').default(''),
  edit: z.string().regex(/^\d+$/).catch('').default(''),
  new: z
    .union([z.string(), z.boolean()])
    .optional()
    .transform((value) => value === 'true' || value === true)
    .catch(false),
});

export type Search = z.output<typeof validateSearch>;
