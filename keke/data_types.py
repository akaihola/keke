from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import NewType, NotRequired, TypedDict

Role = NewType("Role", str)
MessageContent = NewType("MessageContent", str)
SenderName = NewType("SenderName", str)


class OpenAiMessage(TypedDict):
    role: Role
    content: MessageContent
    name: NotRequired[SenderName]


KEKE_PREFIX = "*Keke:* "


@dataclass
class ChatMessage(ABC):
    timestamp: datetime
    text: MessageContent
    author: str

    @abstractmethod
    def to_dict(self) -> OpenAiMessage:
        ...


ChatName = NewType("GroupName", str)
