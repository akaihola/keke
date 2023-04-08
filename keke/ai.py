import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence, cast

import openai

from keke.data_types import ChatMessage, MessageContent, OpenAiMessage, Role
from keke.tokens import num_tokens_from_messages

logger = logging.getLogger(__name__)
openai.api_key = os.environ["OPENAI_API_KEY"]


def get_initial_prompt() -> MessageContent:
    return MessageContent(Path("prompts/initial.txt").read_text())


@contextmanager
def progress(message: str) -> Iterator[None]:
    print(f"\r{message}", end="", flush=True)
    yield
    clear = len(message) * " "
    print(f"\r{clear}\r", end="", flush=True)


def interact(messages: Sequence[ChatMessage]) -> str:
    conversation = [
        OpenAiMessage(role=Role("user"), content=get_initial_prompt()),
        messages[-1].to_dict(),
    ]
    total_tokens = num_tokens_from_messages(conversation)
    for message in messages[-2::-1]:
        msg = message.to_dict()
        msg_tokens = num_tokens_from_messages([msg])
        if total_tokens + msg_tokens > 4096:
            break
        total_tokens += msg_tokens
        conversation.insert(1, msg)
    with progress(
        f"Prompting for completion to {len(conversation)} messages"
        f" with {total_tokens} tokens"
    ):
        response = openai.ChatCompletion.create(  # type: ignore[no-untyped-call]
            model="gpt-3.5-turbo", messages=conversation
        )
    content = cast(str, response.choices[0].message.content)
    tokens = response.usage.completion_tokens
    logger.debug(
        f"Got a completion with %d words and %d tokens", len(content.split()), tokens
    )
    return content
