from adapters.base import PlatformAdapter


class SlackAdapter(PlatformAdapter):
    def __init__(self, client):  # slack_sdk WebClient
        self.client = client

    def send_dm(self, user_id, text, blocks=None):
        self.client.chat_postMessage(channel=user_id, text=text, blocks=blocks)

    def post_to_channel(self, channel_id, text, blocks=None):
        self.client.chat_postMessage(channel=channel_id, text=text, blocks=blocks)

    def get_user_info(self, user_id):
        r = self.client.users_info(user=user_id)
        u = r["user"]
        return {
            "id": user_id,
            "name": u.get("real_name") or u.get("name", ""),
            "email": u.get("profile", {}).get("email", ""),
            "tz": u.get("tz", "UTC"),
        }

    def get_platform(self):
        return "slack"
