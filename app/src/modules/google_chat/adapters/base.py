from abc import ABC, abstractmethod


class PlatformAdapter(ABC):
    @abstractmethod
    def send_dm(self, user_id: str, text: str, blocks=None) -> None: ...

    @abstractmethod
    def post_to_channel(self, channel_id: str, text: str, blocks=None) -> None: ...

    @abstractmethod
    def get_user_info(self, user_id: str) -> dict: ...

    # returns {"id": str, "name": str, "email": str, "tz": str}

    @abstractmethod
    def get_platform(self) -> str: ...

    # returns "slack" | "google_chat" | "teams"
