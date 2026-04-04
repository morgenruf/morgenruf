# Changelog

All notable changes to Morgenruf will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-04-04

### Added

- Multi-workspace OAuth support with PostgreSQL installation store
- Web dashboard for workspace configuration
- Block Kit UI: standup creation modal, DM prompts, App Home tab
- S&P advanced features: user avatar display, Jira/Zendesk issue auto-linking, webhooks with HMAC signing, edit-after-submit window, group-by-question view
- 5 email templates (welcome, first standup, weekly digest, inactive nudge, release announcement)
- Automatic DB migrations as Helm pre-install/pre-upgrade hook
- Security hardening: CSRF protection, SSRF blocking, non-root Docker container, K8s securityContext

### Changed

- Refactored from single-workspace to multi-workspace architecture
- Upgraded Helm chart to v0.2.0 with bundled PostgreSQL (Bitnami)

## [0.1.0] - 2026-03-01

### Added

- Initial release
- Basic Slack standup bot with slash command
- Single-workspace support
- Helm chart v0.1.0
- Docker image published to ghcr.io
