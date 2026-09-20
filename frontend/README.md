# Morgenruf frontend

React and TypeScript run as a Vite SPA. Tailwind 4 and local shadcn/ui primitives provide the visual system; React Router owns URLs and TanStack Query owns server state. The Python backend remains in the sibling `app` workspace.

## Development

Run `tilt up` from the repository root to start the database, backend, and Vite with dependencies and migrations handled automatically. The frontend opens at `http://localhost:3006/dashboard/` and supports hot reload. Follow [the contributor guide](../CONTRIBUTING.md#development-setup) for prerequisites, authentication, tunnels, port overrides, and shutdown.

For a standalone Vite server alongside Compose, run `pnpm install --frozen-lockfile` and `pnpm dev`. This server runs on port 5173 and proxies backend routes to `http://localhost:3006`; set `API_PROXY_TARGET` to change that target. Tilt sets the proxy target and public origin itself.

## Formatting

Run `pnpm format` to format the frontend or `pnpm format:check` to check it without writing changes. Both commands work from the repository root and from `frontend/`, using the shared `.prettierrc.json` and `.prettierignore`. CI runs the same check; generated API code and build/test artifacts are excluded.

The `@ianvs/prettier-plugin-sort-imports` plugin sorts imports into groups separated by blank lines: Node built-ins, external packages (React first), `@/` aliases, and relative imports. Type imports stay with their source group. Side-effect imports such as stylesheets and test setup keep their ordering boundaries.

When opening the repository root in VS Code, install the recommended **Prettier - Code formatter** extension to enable format-on-save for JavaScript, TypeScript, JSX/TSX, CSS, and JSON. Markdown prose keeps its existing line wrapping. Prettier [preserves intentional blank lines](https://prettier.io/docs/rationale#empty-lines) between logical steps, so add those groupings as you write code.

## Feature ownership

`src/app` assembles providers and lazy routes. `src/common` contains shared UI, layouts, session hooks, theme, transport, and utilities. Each `src/modules/<feature>` owns its pages, query hooks, forms, feature-specific components, and colocated tests. Shared code must not import features, and features must not import another feature's implementation; ESLint enforces both boundaries. Extract reusable UI into common code only when there is an actual second consumer.

Routes compose feature pages and supply navigation metadata. Use URL search parameters for shareable filters, React state for transient UI, and React Hook Form for editing. Avoid storing API data in a second state container. The workspace's permissions and module availability come from the backend; frontend controls reflect them, while API authorization remains authoritative.

## Unit test organization

Place frontend unit tests in a `__test__` subfolder of the directory that owns them, using the exact singular folder name and retaining the `.test.ts` or `.test.tsx` filename. Create the folder only where tests exist. For example:

- `src/common/components/__test__/secret-panel.test.tsx`
- `src/common/api/__test__/client.test.ts`
- `src/modules/analytics/__test__/analytics-utils.test.ts`

Shared test setup and helpers stay in `src/test`; shared infrastructure test suites live in `src/test/__test__`. Playwright tests stay in `e2e`. Run unit tests with `pnpm test` or use `pnpm test:watch` from `frontend/` during development.

## API and query conventions

Backend schemas generate `app/openapi.json`, which generates `src/common/api/generated`. Run `pnpm api:generate` after backend contract edits. Never hand-edit those artifacts or create duplicate request/response interfaces. Import generated types or infer them from generated client methods.

Use the single `api` facade from `common/api/client` inside feature query hooks. Query keys start with `['workspace', teamId, feature]` and include filters; pass TanStack's AbortSignal to generated requests. Mutations explicitly invalidate affected keys. Queries are fresh for 30 seconds and do not retry automatically; mutation failures have one shared toast owner. Session expiry clears cached workspace data. CSRF tokens remain in memory and are attached by the shared transport.

Keep newly created keys and webhook secrets only in component state, and clear them on dismissal. Secret-returning mutations transfer secrets directly to that state and return no secret to the mutation cache. Do not persist server data, authentication, or secrets in browser storage.

## UI conventions

Use semantic theme tokens and shadcn primitives under `common/components/ui`. The shell follows Hostleaf's compact navigation with Morgenruf branding. Feature pages use the shared page header, loading, error, and empty states; forms remain keyboard accessible. User-authored Slack text is rendered as React nodes using `SlackText`, never as injected HTML. Fonts and application assets are bundled locally.

## Production routing

The independent Nginx image serves the SPA and proxies explicit backend routes. Exact `/dashboard` remains a backend login-token exchange and redirects to `/dashboard/`; nested dashboard screens and `/dashboard/login` belong to React. API and integration namespaces never fall back to SPA HTML. Legacy hash bookmarks are translated to nested routes. Frontend assets retain their existing `/static/` URLs for Slack messages.

Set `BACKEND_URL` on the frontend container and `APP_URL` on the backend to the public frontend origin. Ingress and HTTPRoute point to the frontend service; backend Kubernetes selectors and service identities are preserved. Publish, upgrade, and roll back frontend and backend release tags together.
