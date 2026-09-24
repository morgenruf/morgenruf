import { z } from 'zod';

export const validateSearch = z.object({
  status: z
    .string()
    .optional()
    .catch(undefined)
    .transform((value) => (value === '' ? 'error' : value)),
  result: z.string().optional().catch(undefined),
});

export type Search = z.output<typeof validateSearch>;
