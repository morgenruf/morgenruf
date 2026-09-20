# Frontend conventions

## Unit tests

- Place every frontend unit test directly inside a `__test__` subfolder of its owning directory. Use the exact singular name `__test__` and keep filenames ending in `.test.ts` or `.test.tsx`.
- For example, use `src/common/components/__test__/secret-panel.test.tsx`, `src/common/api/__test__/client.test.ts`, and `src/modules/analytics/__test__/analytics-utils.test.ts`.
- Create `__test__` folders only where tests exist. When moving a test, preserve its filename and directory ownership, and update affected relative imports, mocks, and file-relative URLs.
- Keep shared setup and helpers in `src/test`, shared infrastructure suites in `src/test/__test__`, and Playwright tests in `e2e`.
