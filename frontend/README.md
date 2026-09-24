# Morgenruf frontend

React and TypeScript run in TanStack Start SPA mode with Vite. Tailwind 4 and local shadcn/ui primitives provide the visual system; TanStack Router owns typed file routes and TanStack Query owns server state. The Python backend remains in the sibling `app` workspace.

## Development

Run `tilt up` from the repository root to start the database, backend, and Vite with dependencies and migrations handled automatically. The frontend opens at `http://localhost:3006/dashboard/` and supports hot reload. Follow [the contributor guide](../CONTRIBUTING.md#development-setup) for prerequisites, authentication, tunnels, port overrides, and shutdown.

For a standalone Vite server alongside Compose, run `pnpm install --frozen-lockfile` and `pnpm dev`. This server runs on port 5173 and proxies backend routes to `http://localhost:3006`; set `API_PROXY_TARGET` to change that target. Tilt sets the proxy target and public origin itself.

## Formatting

Run `pnpm format` to format the frontend or `pnpm format:check` to check it without writing changes. Both commands work from the repository root and from `frontend/`, using the shared `.prettierrc.json` and `.prettierignore`. CI runs the same check; generated API code, the generated route tree, and build/test artifacts are excluded.

The `@ianvs/prettier-plugin-sort-imports` plugin sorts imports into groups separated by blank lines: Node built-ins, external packages (React first), `@/` aliases, and relative imports. Type imports stay with their source group. Side-effect imports such as stylesheets and test setup keep their ordering boundaries.

When opening the repository root in VS Code, install the recommended **Prettier - Code formatter** extension to enable format-on-save for JavaScript, TypeScript, JSX/TSX, CSS, and JSON. Markdown prose keeps its existing line wrapping. Prettier [preserves intentional blank lines](https://prettier.io/docs/rationale#empty-lines) between logical steps, so add those groupings as you write code.

## Feature ownership

`src/router.tsx` creates an independent router and application-services instance; `src/routes` composes thin file routes, and `src/app` assembles providers and the dashboard layout. `src/common` contains shared UI, layouts, session hooks, theme, transport, and utilities. Each `src/modules/<feature>` owns its pages, query hooks, forms, feature-specific components, and colocated tests. Shared code must not import features, features must not import another feature's implementation, and neither may import route implementations or the router entry; ESLint enforces these boundaries. Extract reusable UI into common code only when there is an actual second consumer.

Routes compose feature pages and supply typed titles, module requirements, and loading metadata. Keep feature pages, Zod search schemas, and query-option factories in their owning modules. Start’s Vite plugin generates `src/routeTree.gen.ts` and automatically splits route code; commit that file, never edit it manually, and keep `__test__` folders excluded from route discovery. Run `pnpm build` before `pnpm typecheck` after route changes; CI builds and checks that regeneration leaves no tracked diff. Use URL search parameters for shareable filters, React state for transient UI, and React Hook Form for editing. Avoid storing API data in a second state container. The workspace's permissions and module availability come from the backend; frontend controls reflect them, while API authorization remains authoritative.

Dashboard routes use folders: `src/routes/dashboard/route.tsx` defines the neutral parent, `dashboard/login.tsx` stays public, and `dashboard/_authenticated/route.tsx` defines the pathless authenticated layout. A folder’s `route.tsx` defines its parent route, `index.tsx` defines its index, and other files define child routes. The `_authenticated` folder adds no URL segment. Connect follows the same convention under `dashboard/_authenticated/connect/`, with an Outlet-only `route.tsx` and separate index, creation, attendance, and `$programId` routes. Keep route IDs unchanged when reorganizing files so feature `getRouteApi(...)` references remain stable.

## Unit test organization

Place frontend unit tests in a `__test__` subfolder of the directory that owns them, using the exact singular folder name and retaining the `.test.ts` or `.test.tsx` filename. Create the folder only where tests exist. For example:

- `src/common/components/__test__/secret-panel.test.tsx`
- `src/common/api/__test__/client.test.ts`
- `src/modules/analytics/__test__/analytics-utils.test.ts`

Shared test setup and helpers stay in `src/test`; shared infrastructure test suites live in `src/test/__test__`. Playwright tests stay in `e2e`. Run unit tests with `pnpm test` or use `pnpm test:watch` from `frontend/` during development. Browser tests use port 3008 for their fixture backend; when it is occupied, run with an override such as `MORGENRUF_E2E_BACKEND_PORT=3018 pnpm test:e2e`.

## API and query conventions

Backend schemas generate `app/openapi.json`, which generates `src/common/api/generated`. Run `pnpm api:generate` after backend contract edits. Never hand-edit those artifacts or create duplicate request/response interfaces. Import generated types or infer them from generated client methods.

Use the generated API facade from the current application-services instance inside feature query hooks. Every router owns one QueryClient, transport, and in-memory session/CSRF state; loaders and React providers receive the same instance. Share `queryOptions` factories between component hooks and nonblocking route prefetches, and include only API inputs in `loaderDeps`. Local URL filters and dialog state must preserve mounted forms, focus, and scroll. Query keys start with `['workspace', teamId, feature]` and include filters; pass TanStack's AbortSignal to generated requests. Mutations explicitly invalidate affected keys. Queries are fresh for 30 seconds, sessions for 60 seconds, and neither retries automatically; mutation failures have one shared toast owner. Session expiry and identity changes clear cached workspace data. Authenticated routes bootstrap sessions in `beforeLoad`, await required capability checks, and invalidate router context after authentication or module-permission changes. Intent preloading uses `defaultPreloadStaleTime: 0`, leaving freshness to Query. Public-feed errors do not clear authenticated sessions. CSRF tokens remain in memory and are attached by the shared transport.

Keep newly created keys and webhook secrets only in component state, and clear them on dismissal. Secret-returning mutations transfer secrets directly to that state and return no secret to the mutation cache. Do not persist server data, authentication, or secrets in browser storage.

## UI conventions

Use semantic theme tokens and shadcn primitives under `common/components/ui`. The shell follows Hostleaf's compact navigation with Morgenruf branding. Feature pages use the shared page header, loading, error, and empty states; forms remain keyboard accessible. User-authored Slack text is rendered as React nodes using `SlackText`, never as injected HTML. Fonts and application assets are bundled locally.

All charts use the local [EvilCharts](https://evilcharts.com/docs) Recharts components under `common/components/evilcharts`, including compact bars and sparklines. The official area, line, and bar registry sources and their dependencies are checked in with the upstream MIT license; Recharts and Motion remain the rendering dependencies. Local adaptations provide semantic per-point bar colors, visible zero markers, a shared frosted tooltip surface, tooltips that escape table clipping, keyboard focus styles, and reduced-motion support. Use theme tokens for gradients, keep percentage scales at 0–100, and preserve missing-data gaps and exact-value alternatives when adding charts.

## Production routing

The independent Nginx image serves Start’s native `dist/client/_shell.html` and static assets, and proxies explicit backend routes. The root document and startup fallback must be safe to prerender without browser globals, API requests, credentials, or a running backend. The shell contains public skeleton markup for dashboard and public startup views; an inline pathname check selects the visible view before paint, while React hydrates identical markup on every URL. Only `dist/client` is copied into the image; production runs no Node service. The shell is served with `no-cache`, hashed `/assets/` files are immutable, and missing assets return 404. Exact `/dashboard` remains a backend login-token exchange and redirects to `/dashboard/`; nested dashboard screens and `/dashboard/login` belong to React. API and integration namespaces never fall back to SPA HTML. Legacy hash bookmarks are translated to nested routes. Frontend assets retain their existing `/static/` URLs for Slack messages.

Set `BACKEND_URL` on the frontend container and `APP_URL` on the backend to the public frontend origin. Ingress and HTTPRoute point to the frontend service; backend Kubernetes selectors and service identities are preserved. Publish, upgrade, and roll back frontend and backend release tags together.

## Preview and production checks

Run `pnpm preview` with Docker running to build and serve the production Nginx image at `http://127.0.0.1:4173/dashboard/`. The preview proxies to `http://host.docker.internal:3006` by default; use `BACKEND_URL` for another container-reachable backend URL and `MORGENRUF_PREVIEW_PORT` for another local port. Set the backend’s `APP_URL` to the preview origin when testing OAuth redirects. Stop it with Ctrl+C. This tests the same static shell fallback and proxy configuration as deployment.

Run `pnpm test:e2e:production` after installing Playwright Chromium and the Python test dependencies. It builds the image without application credentials, starts the isolated fixture backend, and tests Nginx on port 5175. Coverage includes shell privacy, hydration and deep-link refreshes, backend login-token exchange, legacy bookmarks, public pages, proxy exclusions, asset caching, and missing assets. Set `MORGENRUF_E2E_BACKEND_PORT` if the production fixture port 3009 is occupied (development browser tests use 3008). The fixture is never included in the image.
