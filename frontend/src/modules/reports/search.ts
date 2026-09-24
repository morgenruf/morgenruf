import { z } from 'zod';

export const validateSearch = z.object({
  date_from: z
    .union([z.literal(''), z.iso.date()])
    .catch('')
    .default(''),
  date_to: z
    .union([z.literal(''), z.iso.date()])
    .catch('')
    .default(''),
  user_id: z.string().catch('').default(''),
});

export type Search = z.output<typeof validateSearch>;
