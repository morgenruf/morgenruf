# Contributing to Morgenruf

Morgenruf is open source and all contributions are welcome — whether that's a bug report, a feature request, documentation improvement, or a pull request. Thank you for taking the time to contribute!

## Development setup

```bash
# 1. Clone the repo
git clone https://github.com/morgenruf/morgenruf
cd morgenruf

# 2. Create and activate a Python virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r app/requirements.txt

# 4. Set up configuration
cp app/.env.example app/.env

# 5. Run the bot locally
cd app && python src/main.py
```

> You will need a Slack app with the appropriate OAuth scopes and a configured Bot Token. See the README for full Slack app setup instructions.

## Project structure

```
app/
  src/           # Flask + slack-bolt application source
  migrations/    # Alembic database migration scripts
  helm/          # Helm chart for Kubernetes deployment
website/         # Marketing / docs website source
brand/           # Logo and brand assets
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

```bash
python -m pytest
```

> The full test suite is coming soon. In the meantime, please test your changes locally against a real Slack workspace and document what you tested in the PR.

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
