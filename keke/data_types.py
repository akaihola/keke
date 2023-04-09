from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import NewType, NotRequired, TypedDict

Role = NewType("Role", str)
WhatsAppMarkup = NewType("WhatsAppMarkup", str)
SenderName = NewType("SenderName", str)


class OpenAiMessage(TypedDict):
    role: Role
    content: WhatsAppMarkup
    name: NotRequired[SenderName]


KEKE_PREFIX = "*Keke:* "


@dataclass
class ChatMessage(ABC):
    timestamp: datetime
    text: WhatsAppMarkup
    author: str

    @abstractmethod
    def to_dict(self) -> OpenAiMessage:
        ...


ChatName = NewType("ChatName", str)
