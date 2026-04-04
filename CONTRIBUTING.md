# Contributing to Morgenruf

Thanks for your interest! Here's how to get started.

## Development setup

```bash
git clone https://github.com/morgenruf/morgenruf
cd morgenruf/app
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && cp teams.yaml.example teams.yaml
python src/main.py
```

## Commit convention

We use [Conventional Commits](https://www.conventionalcommits.org):

```
feat: add weekly summary command
fix: handle missing slack_id in teams.yaml
docs: update helm deployment guide
chore: bump python to 3.12
```

This drives automated versioning via release-please.

## Pull requests

1. Fork → feature branch → PR against `main`
2. One PR per feature/fix
3. Include tests for new behaviour
4. Update docs if behaviour changes

## Reporting issues

Use [GitHub Issues](https://github.com/morgenruf/morgenruf/issues) for bugs.
Use [Discussions](https://github.com/morgenruf/morgenruf/discussions) for questions and ideas.

## Support

Email: [support@morgenruf.dev](mailto:support@morgenruf.dev)
