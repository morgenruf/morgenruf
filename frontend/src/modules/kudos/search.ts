import { z } from 'zod';

export const validateSearch = z.object({
  days: z
    .union([z.string(), z.number()])
    .optional()
    .transform((value) => {
      const days = Number(value);

      return days === 7 || days === 30 || days === 90 ? days : 30;
    })
    .catch(30),
});

export type Search = z.output<typeof validateSearch>;
