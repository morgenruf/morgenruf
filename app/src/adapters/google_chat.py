"""Google Chat adapter — uses Chat API v1 with service account auth."""
import json
import logging
import requests
from adapters.base import PlatformAdapter

logger = logging.getLogger(__name__)

GOOGLE_CHAT_API = "https://chat.googleapis.com/v1"


class GoogleChatAdapter(PlatformAdapter):
    def __init__(self, credentials_json: str):
        """credentials_json: service account JSON string from GOOGLE_CREDENTIALS env var"""
        self._creds_data = json.loads(credentials_json)
        self._token = None
        self._token_expiry = 0

    def _get_token(self) -> str:
        import time
        import jwt as pyjwt

        now = int(time.time())
        if self._token and now < self._token_expiry - 60:
            return self._token

        payload = {
            "iss": self._creds_data["client_email"],
            "scope": "https://www.googleapis.com/auth/chat.bot",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3600,
        }
        signed = pyjwt.encode(payload, self._creds_data["private_key"], algorithm="RS256")
        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": signed,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = now + data.get("expires_in", 3600)
        return self._token

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def send_dm(self, user_id: str, text: str, blocks=None) -> None:
        if not user_id.startswith("users/"):
            user_id = f"users/{user_id}"
        # Try to find existing DM space
        resp = requests.post(
            f"{GOOGLE_CHAT_API}/spaces:findDirectMessage",
            params={"name": user_id},
            headers=self._headers(),
            timeout=10,
        )
        if resp.status_code == 404:
            resp = requests.post(
                f"{GOOGLE_CHAT_API}/spaces",
                json={"spaceType": "DIRECT_MESSAGE", "singleUserBotDm": True},
                headers=self._headers(),
                timeout=10,
            )
        resp.raise_for_status()
        space_name = resp.json().get("name")
        card = _text_to_card(text) if not blocks else blocks
        requests.post(
            f"{GOOGLE_CHAT_API}/{space_name}/messages",
            json={"text": text, "cardsV2": card} if card else {"text": text},
            headers=self._headers(),
            timeout=10,
        )

    def post_to_channel(self, channel_id: str, text: str, blocks=None) -> None:
        if not channel_id.startswith("spaces/"):
            channel_id = f"spaces/{channel_id}"
        requests.post(
            f"{GOOGLE_CHAT_API}/{channel_id}/messages",
            json={"text": text},
            headers=self._headers(),
            timeout=10,
        )

    def get_user_info(self, user_id: str) -> dict:
        if not user_id.startswith("users/"):
            user_id = f"users/{user_id}"
        resp = requests.get(
            f"{GOOGLE_CHAT_API}/{user_id}",
            headers=self._headers(),
            timeout=10,
        )
        if resp.ok:
            u = resp.json()
            return {
                "id": user_id,
                "name": u.get("displayName", ""),
                "email": u.get("domainId", ""),
                "tz": "UTC",
            }
        return {"id": user_id, "name": user_id, "email": "", "tz": "UTC"}

    def get_platform(self):
        return "google_chat"


def _text_to_card(text: str) -> list:
    """Convert plain text to a simple Google Chat Card v2."""
    return [{"card": {"sections": [{"widgets": [{"textParagraph": {"text": text}}]}]}}]
