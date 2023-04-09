from datetime import datetime

import pytest

from keke.whatsapp import WhatsAppChatState, parse_author_and_date, unrender_message


@pytest.mark.kwparametrize(
    dict(msg_html="<span></span>", expected=""),
    dict(msg_html="<span>foo</span>", expected="foo"),
    dict(
        msg_html='<span><a href="http://hst/pth?a=<foo>">link</a></span>',
        expected="link",
    ),
    dict(
        msg_html=(
            "<span>"
            "Link:"
            ' <a href="http://hst/pth?tz=Europe/Helsinki&amp;key=<API-key>"'
            ' title="http://hst/pth?tz=Europe/Helsinki&amp;key=<API-key>"'
            ' target="_blank"'
            ' rel="noopener noreferrer"'
            ' class="_11JPr selectable-text copyable-text">'
            "https://hst/pth?tz=Europe/Helsinki&amp;key=&lt;API-key&gt;"
            "</a>."
            " Here you go!</span>"
        ),
        expected=(
            "Link: https://hst/pth?tz=Europe/Helsinki&key=<API-key>. Here you go!"
        ),
    ),
    dict(
        msg_html=(
            "<span>"
            '<strong class="_11JPr selectable-text copyable-text"'
            ' data-app-text-template="*${appText}*">'
            "Keke:"
            "</strong>"
            " Hi! Link:"
            ' <a href="http://hst/pth?tz=Europe/Helsinki&amp;key=<API-key>"'
            ' title="http://hst/pth?tz=Europe/Helsinki&amp;key=<API-key>"'
            ' target="_blank"'
            ' rel="noopener noreferrer"'
            ' class="_11JPr selectable-text copyable-text">'
            "https://hst/pth?tz=Europe/Helsinki&amp;key=&lt;API-key&gt;"
            "</a>."
            " Here you go!</span>"
        ),
        expected=(
            "*Keke:* Hi! Link: https://hst/pth?tz=Europe/Helsinki&key=<API-key>."
            " Here you go!"
        ),
    ),
    dict(
        msg_html=(
            "<span>"
            '<strong class="_11JPr selectable-text copyable-text"'
            ' data-app-text-template="*${appText}*">'
            "Keke:"
            "</strong>"
            " Happy?"
            "</span>"
        ),
        expected="*Keke:* Happy?",
    ),
)
def test_unrender_message(msg_html: str, expected: str) -> None:
    assert unrender_message(msg_html) == expected


@pytest.mark.kwparametrize(
    dict(
        date_author="[18.13, 9.4.2023] Antti Kaihola: ",
        expect_author="Antti Kaihola",
        expect_date=datetime(2023, 4, 9, 18, 13),
    ),
    dict(
        date_author="[6:57 pm, 19/08/2021] Diksha: ",
        expect_author="Diksha",
        expect_date=datetime(2021, 8, 19, 18, 57),
    ),
)
def test_parse_author_and_date(
    date_author: str, expect_author: str, expect_date: datetime
) -> None:
    state = WhatsAppChatState()
    author, date, state = parse_author_and_date(date_author, state)
    assert (author, date) == (expect_author, expect_date)
