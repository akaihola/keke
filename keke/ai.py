import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence, cast

import openai

from keke.data_types import ChatMessage, ChatName, WhatsAppMarkup, OpenAiMessage, Role
from keke.tokens import num_tokens_from_messages

logger = logging.getLogger(__name__)
openai.api_key = os.environ["OPENAI_API_KEY"]


def get_initial_prompt(chat_title: ChatName) -> WhatsAppMarkup:
    chat_specific_path = Path(f"prompts/{chat_title}/initial.txt")
    path = (
        chat_specific_path
        if chat_specific_path.exists()
        else Path("prompts/initial.txt")
    )
    return WhatsAppMarkup(path.read_text())


@contextmanager
def progress(message: str) -> Iterator[None]:
    print(f"\r{message}", end="", flush=True)
    yield
    clear = len(message) * " "
    print(f"\r{clear}\r", end="", flush=True)


def interact(chat_title: ChatName, messages: Sequence[ChatMessage]) -> str:
    world = OpenAiMessage(role=Role("user"), content=get_initial_prompt(chat_title))
    next_role = None
    conversation: list[OpenAiMessage] = []
    for message in reversed(messages):
        msg = message.to_dict()
        if msg["role"] == next_role:
            last = conversation[0]
            old_content = last["content"]
            new_conversation = [
                OpenAiMessage(
                    role=last["role"],
                    content=WhatsAppMarkup(f"{msg['content']}\n\n{old_content}"),
                )
            ] + conversation[1:]
        else:
            new_conversation = [msg] + conversation
            next_role = msg["role"]
        if num_tokens_from_messages([world] + new_conversation) > 3500:
            break
        conversation = new_conversation
    conversation = [world] + conversation
    logger.debug(str(conversation))
    with progress(f"Prompting for completion to {len(conversation)} messages"):
        response = openai.ChatCompletion.create(  # type: ignore[no-untyped-call]
            model="gpt-3.5-turbo", messages=conversation
        )
    content = cast(str, response.choices[0].message.content)
    tokens = response.usage.completion_tokens
    logger.debug(
        f"Got a completion with %d words and %d tokens", len(content.split()), tokens
    )
    return content
