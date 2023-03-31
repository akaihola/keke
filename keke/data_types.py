from dataclasses import dataclass
from datetime import datetime
from typing import NotRequired, TypedDict


class OpenAiMessage(TypedDict):
    role: str
    content: str
    name: NotRequired[str]


KEKE_PREFIX = "*Keke:* "


@dataclass
class WhatsAppMessage:
    timestamp: datetime
    msgid: str
    author: str
    text: str = ""

    def to_dict(self) -> OpenAiMessage:
        """Return a dictionary representation of the message."""
        author = "" if self.is_from_keke else f"{self.author}: "
        return OpenAiMessage(
            role="assistant" if self.is_from_keke else "user",
            content=f"{author}{self.text_without_keke_prefix}",
        )

    def __str__(self) -> str:
        """Return a string representation of the message."""
        author = "Keke" if self.is_from_keke else self.author
        return f"{self.timestamp:%H.%M} {author}: {self.text_without_keke_prefix}"

    @property
    def text_without_keke_prefix(self) -> str:
        return self.text[len(KEKE_PREFIX) :] if self.is_from_keke else self.text

    @property
    def is_from_keke(self) -> bool:
        """Return whether the message is from Keke."""
        return self.text.startswith(KEKE_PREFIX)
