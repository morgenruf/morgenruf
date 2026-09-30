/**
 * The fewest expected responses a participation rate is judged on.
 *
 * Below this a single missed or filed standup swings the rate by 20 points or
 * more, so "Needs a look" on a standup made this afternoon says nothing about
 * the team. Five is one person over a working week, or five people on one
 * day. Under it the rate is still shown, in a neutral tone, and the verdict
 * reads "Too early to judge".
 */
export const MIN_EXPECTED_FOR_VERDICT = 5;

export function enoughToJudge(expected: number | null | undefined) {
  return (expected ?? 0) >= MIN_EXPECTED_FOR_VERDICT;
}

/**
 * Participation at or above this rate reads as healthy (green) everywhere:
 * the standups list, analytics and the daily trend. Below SLIPPING_RATE it
 * needs a look (red); in between it is slipping (amber).
 */
export const HEALTHY_RATE = 75;
export const SLIPPING_RATE = 40;

export type RateLevel = 'success' | 'warning' | 'destructive';

export function rateLevel(rate: number): RateLevel {
  return rate >= HEALTHY_RATE
    ? 'success'
    : rate >= SLIPPING_RATE
      ? 'warning'
      : 'destructive';
}

/** Written out in full so Tailwind finds the class names. */
export const rateTextClass: Record<RateLevel, string> = {
  success: 'text-success',
  warning: 'text-warning',
  destructive: 'text-destructive',
};
