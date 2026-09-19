# Contributing to Morgenruf

Morgenruf is open source and all contributions are welcome — whether that's a bug report, a feature request, documentation improvement, or a pull request. Thank you for taking the time to contribute!

## Development setup

Use [Tilt](https://docs.tilt.dev/install.html) 0.37 or newer, [uv](https://docs.astral.sh/uv/), Node.js 24, pnpm (the version pinned in `package.json`), and a running Docker engine with Docker Compose. Kubernetes is not required. On macOS, `brew install tilt-dev/tap/tilt uv` installs Tilt and uv.

### Start everything with Tilt

From the repository root:

```bash
tilt up
```

Open <http://localhost:3006/dashboard/>. Tilt installs Python 3.14 and dependencies into `.venv` when needed, installs the pnpm workspace, starts PostgreSQL 16, applies migrations, and launches Flask and Vite. Its dashboard at <http://localhost:10350> shows logs and readiness for `postgres`, `backend`, and `frontend`. Vite handles frontend hot reload; Python changes trigger migrations followed by a backend restart. Flask runs without a debugger or reloader, keeping one scheduler process.

The login page and health endpoint work without credentials. For Slack login and integrations, copy `app/.env.example` to `app/.env` if that file does not already exist, then fill in the relevant credentials. Tilt reads this file without executing it or changing it. Shell environment values take precedence for integration credentials. If no `FLASK_SECRET_KEY` is supplied, a private key is generated under `.local/flask-secret-key` and reused across restarts.

Tilt uses its own persistent `morgenruf-dev_postgres_data` Docker volume, separate from the Compose installation. It always connects the backend to that local database, overriding `DATABASE_URL` and `DB_PASSWORD` from other configuration. The database listens on `127.0.0.1:5436`, using `morgenruf` as the local username, password, and database name. Flask listens on `127.0.0.1:3007`; Vite is the public origin on port 3006 and proxies backend routes. Existing Compose data and Slack installations are not imported into this fresh development database.

Press Ctrl+C to stop Flask and Vite. Then run `tilt down` to remove Tilt's Postgres container and network; its data volume is retained. Restart with `tilt up` to reuse it.

Ports are strict: an occupied port fails visibly instead of silently changing the application URL. If Yaoki already uses Tilt's dashboard port, use `tilt up --port 10351`. If the existing Compose app occupies port 3006, stop that stack first or select another frontend port:

```bash
tilt up --port 10351 -- --frontend-port 3016
```

Other options are `--backend-port`, `--db-port`, and `--env-file`. Options after `--` can also be persisted in a gitignored `tilt_config.json`, for example `{"frontend-port":"3016"}`. Supply the same options when running `tilt down`.

### Stable HTTPS URL for Slack development

Use a named Cloudflare tunnel with a hostname on a domain in your Cloudflare account. Its hostname survives connector and Tilt restarts, so Slack's registered URLs do not need to change. Install `cloudflared` 2025.4.0 or newer (`brew install cloudflared` on macOS).

1. In the Cloudflare dashboard, open **Networking → Tunnels → Create Tunnel** and name the tunnel, for example `morgenruf-dev`. Select your operating system and find the manual command containing `--token`. Save only the token in `.local/cloudflared-token`; Tilt runs the connector itself, so installing a system service is unnecessary. This prompt saves the token without putting it in shell history or displaying it:

   ```bash
   python3 - <<'PY'
   import getpass
   import os
   from pathlib import Path

   directory = Path(".local")
   directory.mkdir(mode=0o700, exist_ok=True)
   target = directory / "cloudflared-token"
   token = getpass.getpass("Paste the Cloudflare tunnel token: ").strip()
   if not token:
       raise SystemExit("Token cannot be empty")
   descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
   with os.fdopen(descriptor, "w") as stream:
       stream.write(token + "\n")
   target.chmod(0o600)
   PY
   ```

2. Add the following options to the repository's gitignored `tilt_config.json`, preserving any existing port or environment-file settings. Replace `dev.example.com` with your chosen hostname:

   ```json
   {
     "app-url": "https://dev.example.com",
     "tunnel-token-file": ".local/cloudflared-token"
   }
   ```

3. Run `tilt up`. The optional `tunnel` resource starts after the frontend and reads the private token file. If Tilt is already running, it reloads the configuration automatically. Wait for Cloudflare to show the connector as **Healthy**, then finish the tunnel creation screen.
4. Open the tunnel's **Routes → Add route → Published application**. Set the hostname to `dev.example.com`, leave the path blank, and set the service URL to `http://127.0.0.1:3006`. Cloudflare creates the DNS record. If you use another frontend port, use that port here too.
5. If the domain has a wildcard Worker route, add a more specific entry under the domain's **Workers Routes**: `dev.example.com/*` with **Worker: None**. This lets this hostname reach the tunnel instead of the wildcard Worker. Keep the existing wildcard route for the other hostnames.
6. Update the development Slack app's URLs using the same origin. In **App Manifest**, replace the previous origin in the URL fields while preserving the app's other settings. Verify the Events API URL when prompted and save the changes.

| Slack setting | URL |
| --- | --- |
| OAuth & Permissions → Redirect URLs | `https://dev.example.com/oauth/callback` |
| Event Subscriptions → Request URL | `https://dev.example.com/slack/events` |
| Every slash command → Request URL | `https://dev.example.com/slack/events` |
| Interactivity & Shortcuts → Request URL | `https://dev.example.com/slack/interactions` |

Check `https://dev.example.com/healthz`: Morgenruf returns JSON containing `"status":"ok"` and `"jobs"`. A plain `ok` response or an unexpected 404 can mean a wildcard Worker is intercepting the hostname. Open `https://dev.example.com/dashboard/` and start a fresh Slack login or installation from that origin. The `/install` URL starts installation into this development database. If Zoom is enabled, update its callback registration to the same origin as well.

From then on, run `tilt up` and use the same HTTPS dashboard URL. Ctrl+C stops the local servers and tunnel; the Cloudflare hostname and Slack configuration remain registered. The URL is available again when Tilt starts. The `.local/` directory and `tilt_config.json` are ignored by Git. Keep the token private and replace its file if you rotate the tunnel token in Cloudflare. Without `tunnel-token-file`, Tilt starts only the local app and database.

The tunnel's readiness probe uses `127.0.0.1:3008/ready` and turns healthy when the connector has an active Cloudflare connection. Override `tunnel-metrics-port` if that port is occupied. The public `/healthz` check additionally verifies DNS and hostname routing to Morgenruf.

Tilt sets `APP_URL` to `app-url`, overriding the value in `app/.env`. It enables secure cookies for HTTPS and allows the chosen hostname through Vite. Changing only `APP_URL` in `app/.env` does not change Tilt's OAuth redirect. Keep the tunnel target on `127.0.0.1` and stop any older Compose app occupying the frontend port.

### Temporary tunnel alternative

If you do not have a domain in Cloudflare, run a quick tunnel in a separate terminal:

```bash
cloudflared tunnel --url http://127.0.0.1:3006
tilt up -- --app-url https://your-tunnel.trycloudflare.com
```

Remove `tunnel-token-file` from `tilt_config.json` when using this alternative. You can save the current origin with `{"app-url":"https://your-tunnel.trycloudflare.com"}`, but this does not make a quick tunnel persistent. Each new quick-tunnel process gets a new hostname, requiring updates to Tilt and all integration URLs in the table above. An old hostname may stop resolving or return Cloudflare error 1033 even while the local app is healthy. If Slack reports `redirect_uri did not match any configured URIs`, compare the URI in the error with the development app's saved OAuth redirect and start a fresh login after correcting them.

### Container-only alternative

The local Compose configuration builds this checkout, starts PostgreSQL 16, and applies migrations before starting the app. Use it to test the production frontend gateway, or when you prefer containers for both application services.

The local override runs Flask and the scheduler in one process, with the debugger and reloader disabled, so database connections are not shared across a Gunicorn fork. This launch configuration is for local development.

```bash
# 1. Clone the repo
git clone https://github.com/morgenruf/morgenruf
cd morgenruf

# 2. Create a Python environment and install application and test dependencies
uv venv --python 3.14
uv pip install -r app/requirements.txt pytest pytest-mock pytest-cov ruff

# 3. Create configuration for a fresh checkout (preserve an existing .env)
cp app/.env.example app/.env
chmod 600 app/.env
```

Edit `app/.env`:

- Set `DB_PASSWORD` to a generated value: `openssl rand -hex 24`.
- Set `FLASK_SECRET_KEY` to a different generated value: `openssl rand -hex 32`.
- Set `APP_URL=http://localhost:3006` to match the local Compose port.

Leave Slack and optional service credentials blank until you are ready to connect them. Local startup and tests work without a Slack app; dashboard login and bot features require a Slack installation.

```bash
# 4. Build and start the app and its database
cd app
docker compose -p morgenruf -f docker-compose.yml -f docker-compose.local.yml up -d --build

# 5. Verify startup
curl --fail http://localhost:3006/healthz
```

Open <http://localhost:3006/dashboard/> for the React application. Signing in requires a Slack installation; `/healthz` verifies the backend before Slack is configured. Nginx serves the frontend and proxies API and integration requests to the separate Flask service. The local override preserves port 3006 and explicitly disables secure cookies for local HTTP. Backend and containerized frontend source changes take effect after rerunning the build/start command above.

Run these commands from `app/` to inspect or stop the local services:

```bash
docker compose -p morgenruf -f docker-compose.yml -f docker-compose.local.yml ps -a
docker compose -p morgenruf -f docker-compose.yml -f docker-compose.local.yml logs --tail=100 app
docker compose -p morgenruf -f docker-compose.yml -f docker-compose.local.yml down
```

Stopping with `down` preserves the database volume. Keep the configured `DB_PASSWORD`: changing `.env` does not change the password of an existing PostgreSQL database.

When connecting Slack, follow the [Slack setup walkthrough](README.md#docker-and-mac-quickstart), point the HTTPS tunnel at port **3006**, and set `APP_URL` to its public URL. Replace the hosted URLs in `slack-manifest.yaml` with your own URL. Add your Slack client ID, client secret, and signing secret to `app/.env`, then rerun the Compose `up -d` command so the container receives the updated environment.

## Frontend development

Tilt already starts Vite on port 3006; no second development server is needed. To run Vite separately alongside the container-only setup, install the workspace dependencies and start it from the repository root:

```bash
corepack enable
pnpm install --frozen-lockfile
pnpm dev
```

Vite runs at <http://localhost:5173> and proxies APIs and authentication to the local Compose gateway at port 3006. Override `API_PROXY_TARGET` to use another backend gateway. For OAuth through Vite, set `APP_URL=http://localhost:5173` in `app/.env` and rebuild/restart the local services; configure Slack's callback URL using the same public origin (or its HTTPS tunnel). When using only the built frontend on port 3006, keep `APP_URL=http://localhost:3006`. Do not expose local HTTP cookie settings in production.

```bash
pnpm format:check
pnpm typecheck
pnpm lint
pnpm test
pnpm build
pnpm --filter @morgenruf/frontend exec playwright install chromium
pnpm --filter @morgenruf/frontend test:e2e
```

Run `pnpm format` to apply the shared Prettier formatting rules to the frontend. Formatting commands also work from `frontend/`. See [Frontend formatting](frontend/README.md#formatting) for editor setup and excluded generated files.

Browser tests start an isolated test backend with in-memory fixtures and mocked integrations; they do not contact Slack, Zoom, email providers, or your database. The Python test environment must be installed first. The fixture runner is test-only and is never packaged in the backend image.

## API contracts

Backend Marshmallow schemas and Flask-smorest route metadata are the source of truth for browser requests, responses, and errors. Edit those definitions, then regenerate both checked-in artifacts:

```bash
pnpm api:generate
pnpm api:check
```

Generation invokes the offline HTTP factory and needs neither running services nor credentials. `api:check` writes temporary artifacts and fails when either the OpenAPI document or TypeScript client differs. Frontend builds use the committed client and do not start Python or call a live backend. The deployed schema is available at `/openapi.json`.

Never edit generated TypeScript or handwrite duplicate API DTOs. Feature hooks call the generated client and return its types. Add fields to backend schemas before using them in React. See [Frontend architecture](frontend/README.md) for code organization and state conventions.

## Project structure

```text
app/
  src/core/       # Flask, workspace services, API schemas, core SQL migrations
  src/modules/    # Feature services, routes, schemas, and SQL migrations
  openapi.json    # Generated browser API contract
  helm/           # Backend and frontend Kubernetes resources
frontend/
  src/app/        # Bootstrap, router, root providers
  src/common/     # API client, shared UI, auth, theme, utilities
  src/modules/    # Feature pages, hooks, forms, and tests
  e2e/            # Playwright tests and isolated test backend
scripts/          # Deterministic API generation and drift checks
brand/            # Logo and brand assets
```

## Making changes

**Branch naming:**

| Type | Prefix | Example |
|------|--------|---------|
| New feature | `feat/` | `feat/group-by-question` |
| Bug fix | `fix/` | `fix/duplicate-standup-dm` |
| Docs | `docs/` | `docs/helm-deployment-guide` |
| Refactor | `refactor/` | `refactor/oauth-install-store` |

**Commit messages** follow [Conventional Commits](https://www.conventionalcommits.org):

```
feat: add weekly summary slash command
fix: handle missing slack_id gracefully
docs: update helm deployment guide
chore: bump slack-bolt to 1.19
```

## Submitting a PR

1. **Fork** the repository and create your branch from `main`.
2. **Make your changes**, keeping commits focused and well-described.
3. **Open a pull request** against `main` using the PR template.
4. A maintainer will review your PR. Please address any requested changes.

## Running tests

From the repository root:

```bash
cd app
../.venv/bin/python -m pytest
```

Run tests from `app/`; some tests read source files relative to that directory. The unit suite uses mocked integrations and does not require Slack credentials or a running database. Verify changes involving Slack delivery against a real workspace as well.

From the repository root, check code style with:

```bash
.venv/bin/ruff check app/src
.venv/bin/ruff format app/src --check
```

The Tilt environment helper has isolated tests that do not start services or read your credentials:

```bash
.venv/bin/python -m pytest scripts/tests -q
```

To smoke-test the entire local startup, use `tilt ci --timeout 3m`, then `tilt down`. Use the port and environment-file options above when another stack is already running.

## Code style

- Follow [PEP 8](https://peps.python.org/pep-0008/).
- Type hints are encouraged for new functions.
- Never commit secrets, tokens, or credentials — use environment variables.
- Keep functions small and focused; prefer clarity over cleverness.

## Reporting bugs

Please use the [Bug Report issue template](https://github.com/morgenruf/morgenruf/issues/new?template=bug_report.md). Include as much detail as possible: steps to reproduce, expected vs actual behavior, logs, and environment info.

## Community

Have a question or idea? Start a thread in [GitHub Discussions](https://github.com/morgenruf/morgenruf/discussions) — that's the best place for open-ended conversation.

## License

By contributing to Morgenruf, you agree that your contributions will be licensed under the [Apache 2.0 License](LICENSE).
