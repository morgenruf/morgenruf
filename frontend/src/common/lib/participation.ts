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
