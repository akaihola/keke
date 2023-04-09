import pytest

from keke.whatsapp import unrender_message


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
