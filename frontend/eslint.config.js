import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';
import tseslint from 'typescript-eslint';

import boundaries from './eslint/architecture.mjs';

export default tseslint.config(
  {
    ignores: [
      'dist',
      '.vite',
      '.tanstack',
      'src/routeTree.gen.ts',
      'src/common/api/generated',
      'node_modules',
      'playwright-report',
      'test-results',
      'playwright-report-production',
      'test-results-production',
    ],
  },

  js.configs.recommended,
  ...tseslint.configs.recommended,

  {
    files: ['scripts/**/*.mjs'],
    languageOptions: { globals: globals.node },
  },

  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': [
        'warn',
        {
          allowConstantExport: true,
          allowExportNames: [
            'Route',
            'buttonVariants',
            'badgeVariants',
            'tabsListVariants',
            'useSidebar',
          ],
        },
      ],
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/purity': 'off',
      'react-hooks/refs': 'off',
    },
  },

  {
    // Start owns the root document's refresh boundary; test helpers never use HMR.
    files: ['src/routes/__root.tsx', 'src/test/router.tsx'],
    rules: { 'react-refresh/only-export-components': 'off' },
  },

  {
    files: ['src/common/api/services-context.tsx'],
    rules: {
      'react-refresh/only-export-components': [
        'warn',
        {
          allowExportNames: ['useServices', 'useApi', 'useSessionIdentity'],
        },
      ],
    },
  },

  {
    files: ['src/**/*.{ts,tsx}'],
    plugins: { architecture: { rules: { boundaries } } },
    rules: { 'architecture/boundaries': 'error' },
  },
);
