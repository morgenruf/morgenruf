"""PostgreSQL-backed InstallationStore for slack-bolt OAuth."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import db
from slack_sdk.oauth.installation_store import Bot, Installation, InstallationStore

logger = logging.getLogger(__name__)


class PostgresInstallationStore(InstallationStore):
    """Stores and retrieves Slack OAuth installations in PostgreSQL."""

    def save(self, installation: Installation) -> None:
        try:
            # Compute token expiry timestamp from expires_at (epoch) if available
            expires_at_str = None
            if installation.bot_token_expires_at and installation.bot_token_expires_at > 0:
                expires_at_str = datetime.fromtimestamp(
                    installation.bot_token_expires_at, tz=timezone.utc
                ).isoformat()

            db.save_installation(
                team_id=installation.team_id or "",
                team_name=installation.team_name or "",
                bot_token=installation.bot_token or "",
                bot_user_id=installation.bot_user_id or "",
                app_id=installation.app_id or "",
                installed_by_user_id=installation.user_id,
                bot_refresh_token=installation.bot_refresh_token,
                bot_token_expires_at=expires_at_str,
            )
        except Exception as exc:
            logger.error("Failed to save installation for team %s: %s", installation.team_id, exc)
            raise

    def find_installation(
        self,
        *,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        user_id: Optional[str] = None,
        is_enterprise_install: Optional[bool] = False,
    ) -> Optional[Installation]:
        if not team_id:
            return None
        try:
            row = db.get_installation(team_id)
            if not row:
                return None

            # Convert stored expiry back to epoch seconds
            bot_token_expires_at = None
            if row.get("bot_token_expires_at"):
                ts = row["bot_token_expires_at"]
                if hasattr(ts, "timestamp"):
                    bot_token_expires_at = int(ts.timestamp())

            return Installation(
                app_id=row["app_id"],
                enterprise_id=None,
                team_id=row["team_id"],
                team_name=row["team_name"],
                bot_token=row["bot_token"],
                bot_id=row.get("bot_id") or "",
                bot_user_id=row["bot_user_id"],
                bot_refresh_token=row.get("bot_refresh_token"),
                bot_token_expires_at=bot_token_expires_at,
                user_id=row.get("installed_by_user_id") or "",
                installed_at=row.get("installed_at"),
            )
        except Exception as exc:
            logger.error("Failed to find installation for team %s: %s", team_id, exc)
            return None

    def find_bot(
        self,
        *,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        is_enterprise_install: Optional[bool] = False,
    ) -> Optional[Bot]:
        if not team_id:
            return None
        try:
            row = db.get_installation(team_id)
            if not row:
                return None

            bot_token_expires_at = None
            if row.get("bot_token_expires_at"):
                ts = row["bot_token_expires_at"]
                if hasattr(ts, "timestamp"):
                    bot_token_expires_at = int(ts.timestamp())

            return Bot(
                app_id=row["app_id"],
                enterprise_id=None,
                team_id=row["team_id"],
                team_name=row["team_name"],
                bot_token=row["bot_token"],
                bot_id=row.get("bot_id") or "",
                bot_user_id=row["bot_user_id"],
                bot_refresh_token=row.get("bot_refresh_token"),
                bot_token_expires_at=bot_token_expires_at,
                installed_at=row.get("installed_at"),
            )
        except Exception as exc:
            logger.error("Failed to find bot for team %s: %s", team_id, exc)
            return None
