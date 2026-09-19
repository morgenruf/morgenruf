// @vitest-environment node
import { fileURLToPath } from 'node:url';

import { Linter } from 'eslint';
import { describe, expect, it } from 'vitest';

import boundaries from '../../eslint/architecture.mjs';

function check(file: string, code: string) {
  return new Linter().verify(
    code,
    [
      {
        files: ['**/*.{js,ts,tsx}'],
        plugins: { architecture: { rules: { boundaries } } },
        rules: { 'architecture/boundaries': 'error' },
      },
    ],
    { filename: fileURLToPath(new URL(`../${file}`, import.meta.url)) },
  );
}

describe('frontend architecture boundaries', () => {
  it.each([
    "import { x } from '@/modules/kudos/hooks';",
    "import { x } from '../../kudos/hooks';",
    "export { x } from '../../kudos/hooks';",
    "export * from '../../kudos/hooks';",
    "const page=import('../../kudos/pages/kudos-page');",
  ])('blocks cross-feature access: %s', (code) => {
    expect(check('modules/reports/pages/page.tsx', code)).toHaveLength(1);
  });

  it.each([
    "import { x } from '@/modules/kudos/hooks';",
    "import { x } from '../../modules/kudos/hooks';",
    "const page=import('../../app/providers');",
  ])('blocks shared code depending on higher layers: %s', (code) => {
    expect(check('common/lib/util.ts', code)).toHaveLength(1);
  });

  it.each([
    "import { x } from '@/common/lib/utils';",
    "import { x } from '@/modules/reports/hooks';",
    "import { x } from '../hooks';",
  ])(
    'allows a feature to use common code and its own internals: %s',
    (code) => {
      expect(check('modules/reports/pages/page.tsx', code)).toHaveLength(0);
    },
  );

  it('allows the app router to compose features', () => {
    expect(
      check(
        'app/router.ts',
        "const page=import('@/modules/kudos/pages/kudos-page');",
      ),
    ).toHaveLength(0);
  });
});
