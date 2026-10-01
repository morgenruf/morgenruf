# Morgenruf operator runbook

For the hosted instance. Commands assume the Helm release `morgenruf` in
namespace `morgenruf` (as in the README), so the backend Deployment, its
container and the chart secret are `morgenruf`, `morgenruf` and
`morgenruf-secret`. Adjust if yours differ.

```sh
NS=morgenruf
# The database URL the app uses (the chart secret key is DATABASE_URL).
DATABASE_URL=$(kubectl -n $NS get secret morgenruf-secret -o jsonpath='{.data.DATABASE_URL}' | base64 -d)
# A throwaway psql client. The app image has no psql.
psql_pod() { kubectl -n $NS run psql-$RANDOM --rm -i --quiet --restart=Never --image=postgres:16-alpine -- psql "$DATABASE_URL" "$@"; }
```

## Signals

- **Job alerts.** With `ops.alertWebhook` (`MORGENRUF_ALERT_WEBHOOK`) set, the
  scheduler posts to that Slack channel when a job fails or misses its time:
  - ``:warning: Scheduled job `<job_id>` missed its <time> run.`` (cron jobs only)
  - ``:rotating_light: Scheduled job `<job_id>` failed at <time>: <error>``

  Each job and event alerts at most once per 6 hours per pod.
- **Token alerts.** With `ops.email` (`MORGENRUF_OPS_EMAIL`) and a Resend key,
  a failed bot token refresh emails `[Morgenruf] Token refresh failed for team <team_id>`.
- **Probes.** `/livez` checks only the scheduler (startup and liveness probe).
  `/healthz` checks scheduler and database and returns 503 with `"db": false`
  or `"scheduler": false` (readiness probe):

  ```sh
  kubectl -n $NS exec deploy/morgenruf -c morgenruf -- python -c \
    "import urllib.request as u; print(u.urlopen('http://localhost:3000/healthz').read().decode())"
  ```

Job ids that appear in alerts and in `scheduler_runs`:

| Job | id |
| --- | --- |
| Standup for a schedule | `schedule_<team_id>_<schedule_id>` |
| Reminders, reports, nudges | `reminder_schedule_...`, `weekend_reminder_schedule_...`, `report_schedule_...`, `nudge_missing_...` |
| Coffee round | `connect:<team_id>:round:<program_id>` |
| Coffee catch-up sweep | `connect:<team_id>:catchup` |

## Missed coffee round or missed standup

1. Check for a missed or failed alert for the job id above, and `/healthz`.
2. See whether a pod claimed the firing. Every cron firing inserts one row
   into `scheduler_runs (job_id, run_at, claimed_at)`; rows older than 7 days
   are purged nightly.

   ```sh
   psql_pod -c "SELECT job_id, run_at, claimed_at FROM scheduler_runs
                WHERE job_id LIKE '%T0123ABC%' ORDER BY run_at DESC LIMIT 50;"
   ```

   No row means the job never fired (pod down, or more than 5 minutes late,
   which is the misfire grace). A row means it fired; look in the logs for the
   error:

   ```sh
   kubectl -n $NS logs deploy/morgenruf -c morgenruf --since=24h | grep '<job_id>'
   ```
3. Coffee rounds:

   ```sh
   psql_pod -c "SELECT id, program_id, scheduled_for, state, manual, delivery_claimed_at
                FROM connect_rounds WHERE team_id = 'T0123ABC'
                ORDER BY scheduled_for DESC LIMIT 10;"
   ```

   - **Catch-up.** Every 5 minutes `connect:<team>:catchup` starts a round that
     is still due once its time plus 10 minutes has passed, on the same day
     only. A round missed on an earlier day is not started.
   - **Resume.** A round stuck in `pending` or `matched` (up to 24 hours old)
     is resumed by the follow-up sweep. Delivery holds a 10 minute lease in
     `connect_rounds.delivery_claimed_at`, so a pod killed mid delivery is
     picked up by the next sweep once the lease expires.
   - **Start one by hand.** A workspace admin opens the dashboard, Connect,
     the programme, and clicks **Run a round** (calls
     `POST /dashboard/api/connect/programs/<program_id>/run`, which runs with
     `force=True`). There is no slash command or MCP tool for this.
4. Standups have no catch-up: a firing more than 5 minutes late is dropped
   and only the missed alert records it. Non permanent Slack auth errors are
   retried after 60, 300 and 900 seconds. Members can still start their own
   standup with `/standup`; there is no route that re-runs a whole schedule.

## Revoked or expired bot token

- Tokens are refreshed ahead of expiry. On an auth error the app refreshes
  once and retries; if that fails it emails the ops address and logs
  `TOKEN_REFRESH_FAILURE team=<team_id>`.
- `token_revoked`, `invalid_auth`, `account_inactive`, `team_disabled` and
  `not_authed` are treated as permanent: that workspace's standups are
  skipped, not retried. The member sync (every 6 hours) marks the
  installation inactive.
- Check it:

  ```sh
  kubectl -n $NS logs deploy/morgenruf -c morgenruf --since=24h | grep TOKEN_REFRESH_FAILURE
  psql_pod -c "SELECT team_id, team_name, active, deactivated_at, deactivated_reason, bot_token_expires_at
               FROM installations WHERE team_id = 'T0123ABC';"
  ```
- Fix: a workspace admin reinstalls from `https://<app.url>/install`. The
  OAuth callback (`/oauth/callback`) stores the new token and reactivates the
  installation. If Slack sent `tokens_revoked` or `app_uninstalled`, the
  workspace's data was already deleted and the reinstall starts fresh.
- A retired workspace's data is deleted by the nightly sweep
  (`inactive_workspace_sweep`, 03:57 UTC): 24 hours after `account_inactive`
  or a revoked token, 7 days after `invalid_auth` or `not_authed`, never for
  any other reason. It is a dry run unless `PURGE_INACTIVE_WORKSPACES=1`
  (Helm `ops.purgeInactiveWorkspaces`); check what it would delete with:

  ```sh
  kubectl -n $NS logs deploy/morgenruf -c morgenruf --since=24h | grep "Workspace purge"
  ```
  After a purge only a bare `installations` row (tokens cleared, `purged_at`
  set) and the `workspace_history` row remain. A reinstall starts fresh.

## Database down

- Symptoms: `/healthz` 503 with `"db": false`, pods go unready (no traffic),
  `/livez` stays 200 so pods are not restarted. Log line:
  `Health check could not reach the database`.
- While it is down, cron claims cannot be written and jobs run unclaimed;
  anything that needs the database fails and alerts.
- Check reachability from the cluster: `psql_pod -c 'SELECT 1'`.
- External database: fix it at the provider. Bundled one
  (`postgresql.enabled: true`):

  ```sh
  kubectl -n $NS get pods -l app.kubernetes.io/name=morgenruf-postgresql
  kubectl -n $NS logs statefulset/morgenruf-postgresql
  kubectl -n $NS describe pvc data-morgenruf-postgresql-0
  ```
- When it is back, readiness recovers on its own. A migration that failed
  shows in the `migrate` init container: `kubectl -n $NS logs deploy/morgenruf -c migrate`.
  Applied migrations are listed in `schema_migrations`.

## After every rollout

1. Wait for the rollout: `kubectl -n $NS rollout status deploy/morgenruf`.
2. Check health from outside:

   ```sh
   curl -fsS https://api.morgenruf.dev/healthz
   # {"db":true,"jobs":<n>,"scheduler":true,"status":"ok"}
   ```

   `-f` fails on the 503 that `/healthz` returns when the database or the
   scheduler is down. `jobs` should be close to what it was before the rollout.
3. Run the smoke tests in the e2e repo (they hit `https://api.morgenruf.dev`):

   ```sh
   gh workflow run e2e.yml -R morgenruf/e2e-tests -f suite=smoke
   gh run list -R morgenruf/e2e-tests -w e2e.yml -L 1
   ```

   The workflow does not read the `suite` input yet, so a manual run starts
   both the smoke job and the full suite. The smoke job result is the one to
   wait for.
4. If either fails, go to Rollback.

## Rollback

Migrations only move forward. Rolling back the image does not undo schema
changes, so check the release notes before going back across a migration.

```sh
helm -n $NS history morgenruf
helm -n $NS rollback morgenruf <REVISION>
kubectl -n $NS rollout status deploy/morgenruf
```

To pin an exact image instead of a tag (CI scans and signs by digest):

```sh
docker buildx imagetools inspect morgenruf/morgenruf:1.9.4 | grep Digest
docker buildx imagetools inspect morgenruf/morgenruf-frontend:1.9.4 | grep Digest
helm -n $NS upgrade morgenruf morgenruf/morgenruf --reuse-values \
  --set image.digest=sha256:<backend> --set frontend.image.digest=sha256:<frontend>
```

Clear the pin with `--set image.digest= --set frontend.image.digest=`.

## Restore from backup

There is no nightly backup CronJob yet; setting one up is a separate infra
task. Until then, take a dump before any risky change:

```sh
kubectl -n $NS run pgdump --rm -i --quiet --restart=Never --image=postgres:16-alpine -- \
  pg_dump "$DATABASE_URL" --format=custom --no-owner > morgenruf-$(date +%F).dump
```

Restore (stop the app first so the scheduler does not write mid restore):

```sh
kubectl -n $NS scale deploy/morgenruf --replicas=0
kubectl -n $NS run pgrestore --rm -i --quiet --restart=Never --image=postgres:16-alpine -- \
  pg_restore --dbname="$DATABASE_URL" --clean --if-exists --no-owner < morgenruf-2026-09-29.dump
kubectl -n $NS scale deploy/morgenruf --replicas=1
```

The `migrate` init container then applies any migration newer than the dump.

## Shipping logs to Axiom

1. Keep `ops.logFormat: json` (the chart default). App and gunicorn logs are
   then one JSON object per line on stdout with `time`, `level`, `logger`,
   `message`, `exc_info` and any `extra` fields.
2. Follow Axiom's Kubernetes guide, which runs Vector as a DaemonSet with a
   `kubernetes_logs` source and an `axiom` sink, configured through
   `AXIOM_HOST`, `AXIOM_DATASET` and `AXIOM_TOKEN` (an ingest-only token):
   <https://axiom.co/docs/send-data/kubernetes>. Vector sink reference:
   <https://axiom.co/docs/send-data/vector>.
3. Restrict the source to this namespace and parse the `message` field as
   JSON in a Vector `remap` transform so the fields above are queryable.
