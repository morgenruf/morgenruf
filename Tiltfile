# Local development: Postgres in Docker, Flask and Vite on the host.
# No Kubernetes context or production configuration is required.
version_settings(constraint='>=0.37.0')

config.define_string('frontend-port', usage='Public Vite port (default: 3006)')
config.define_string('backend-port', usage='Internal Flask port (default: 3007)')
config.define_string('db-port', usage='Loopback Postgres port (default: 5436)')
config.define_string('app-url', usage='Public origin for OAuth; defaults to the local frontend URL')
config.define_string('env-file', usage='Optional integration credentials file (default: app/.env)')
config.define_string('tunnel-token-file', usage='Optional Cloudflare named-tunnel token file; starts the tunnel with Tilt')
config.define_string('tunnel-metrics-port', usage='Loopback tunnel readiness port (default: 3008)')
cfg = config.parse()

def port_setting(name, default):
    value = int(cfg.get(name, str(default)))
    if value < 1024 or value > 65535:
        fail('%s must be between 1024 and 65535' % name)
    return value

frontend_port = port_setting('frontend-port', 3006)
backend_port = port_setting('backend-port', 3007)
db_port = port_setting('db-port', 5436)
if frontend_port == backend_port or frontend_port == db_port or backend_port == db_port:
    fail('Frontend, backend, and database ports must be different')

frontend_url = 'http://localhost:%s' % frontend_port
backend_url = 'http://127.0.0.1:%s' % backend_port
app_url = cfg.get('app-url', frontend_url)
env_file = cfg.get('env-file', 'app/.env')
tunnel_token_file = cfg.get('tunnel-token-file', '')
if tunnel_token_file:
    tunnel_metrics_port = port_setting('tunnel-metrics-port', 3008)
    if tunnel_metrics_port in [frontend_port, backend_port, db_port]:
        fail('Tunnel readiness port must differ from the frontend, backend, and database ports')
    if not app_url.startswith('https://') or '.trycloudflare.com' in app_url:
        fail('tunnel-token-file requires app-url to be the named tunnel\'s stable HTTPS origin')
    if not os.path.exists(tunnel_token_file):
        fail('Cloudflare tunnel token file does not exist: %s' % tunnel_token_file)
print('Morgenruf public origin: %s (Slack callback: %s/oauth/callback)' % (app_url, app_url.rstrip('/')))

# Native Compose integration lets `tilt down` remove this container while
# retaining the dedicated development volume. It never uses the app's DB URL.
os.putenv('MORGENRUF_DEV_DB_PORT', str(db_port))
docker_compose('dev/docker-compose.yml', project_name='morgenruf-dev', wait=True)
dc_resource('postgres', labels=['infrastructure'], infer_links=False)

dev_args = [
    '--db-port', str(db_port),
    '--backend-port', str(backend_port),
    '--app-url', app_url,
    '--env-file', env_file,
]
python = '.venv/bin/python'
migrate_command = [python, 'scripts/dev.py', 'migrate'] + dev_args

# Tilt dependencies gate initial startup only. Keep installation and migrations
# in this resource's build phase so they also finish before EVERY code restart.
local_resource(
    'backend',
    cmd=[
        'sh', '-eu', '-c',
        '''if [ ! -x .venv/bin/python ]; then uv venv --python 3.14 .venv; fi
uv pip install --python .venv/bin/python -r app/requirements.txt pytest pytest-mock pytest-cov ruff
exec "$@"''',
        'morgenruf-backend',
    ] + migrate_command,
    serve_cmd=[python, 'scripts/dev.py', 'serve'] + dev_args,
    deps=['app/src', 'app/requirements.txt', 'scripts/dev.py', env_file],
    ignore=['**/__pycache__/**', '**/*.pyc'],
    resource_deps=['postgres'],
    readiness_probe=probe(
        http_get=http_get_action(host='127.0.0.1', port=backend_port, path='/healthz'),
        period_secs=2,
    ),
    labels=['application'],
    links=[link(backend_url + '/healthz', 'Backend health')],
)

# Vite owns source-file HMR. Tilt only restarts it after dependencies change,
# and a failed install never starts a server with incomplete dependencies.
local_resource(
    'frontend',
    cmd=['pnpm', 'install', '--frozen-lockfile'],
    serve_cmd=[
        'pnpm', '--filter', '@morgenruf/frontend', 'exec', 'vite',
        '--host', '127.0.0.1', '--port', str(frontend_port), '--strictPort',
    ],
    serve_env={
        'API_PROXY_TARGET': backend_url,
        'MORGENRUF_DEV_APP_URL': app_url,
    },
    deps=['package.json', 'pnpm-lock.yaml', 'pnpm-workspace.yaml', 'frontend/package.json'],
    resource_deps=['backend'],
    readiness_probe=probe(
        http_get=http_get_action(host='127.0.0.1', port=frontend_port, path='/'),
        period_secs=2,
    ),
    labels=['application'],
    links=[link(app_url + '/dashboard/', 'Morgenruf')],
)

# The hostname and frontend route are configured once in Cloudflare. Keep the
# connector under Tilt so restarts reuse that hostname without a second terminal.
# Pass only the file path: the token must never appear in Tilt's command logs.
if tunnel_token_file:
    local_resource(
        'tunnel',
        serve_cmd=[
            'cloudflared', 'tunnel', '--no-autoupdate',
            '--metrics', '127.0.0.1:%s' % tunnel_metrics_port,
            'run', '--token-file', tunnel_token_file,
        ],
        serve_env={'TUNNEL_TOKEN': ''},
        deps=[tunnel_token_file],
        resource_deps=['frontend'],
        readiness_probe=probe(
            http_get=http_get_action(host='127.0.0.1', port=tunnel_metrics_port, path='/ready'),
            period_secs=2,
        ),
        labels=['infrastructure'],
        links=[link(app_url + '/healthz', 'Public tunnel health')],
    )
