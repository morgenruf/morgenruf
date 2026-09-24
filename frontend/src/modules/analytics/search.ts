import { z } from 'zod';

export const validateSearch = z.object({
  days: z
    .union([z.string(), z.number()])
    .optional()
    .transform((value) => (value === '30' || value === 30 ? 30 : 7))
    .catch(7),
  schedule: z.string().catch('').default(''),
  unenrolled: z
    .union([z.string(), z.boolean()])
    .optional()
    .transform((value) => value === 'true' || value === true)
    .catch(false),
});

export type Search = z.output<typeof validateSearch>;
