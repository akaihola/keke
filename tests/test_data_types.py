from datetime import datetime

import pytest

from keke.data_types import WhatsAppMarkup, OpenAiMessage
from keke.whatsapp import WhatsAppMessage, WhatsAppMessageId


@pytest.mark.parametrize(
    "author, text, expect",
    [
        ("Alice", "Hello", {"role": "user", "content": "Alice: Hello"}),
        ("Antti", "*Keke:* Hi there", {"role": "assistant", "content": "Hi there"}),
    ],
)
def test_whatsapp_message_to_dict(
    author: str, text: str, expect: OpenAiMessage
) -> None:
    """Test that the WhatsAppMessage.to_dict() method returns the correct dictionary."""
    message = WhatsAppMessage(
        timestamp=datetime.now(),
        msgid=WhatsAppMessageId("msgid"),
        author=author,
        text=WhatsAppMarkup(text),
    )
    assert message.to_dict() == expect
