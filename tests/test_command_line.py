import pytest

from keke.command_line import retouch_wake_up


@pytest.mark.parametrize(
    "wake_up, expect",
    [
        ("", ""),
        ("foo", r"\bfoo\b"),
        ("foo,", r"\bfoo,"),
        ("^foo,", r"^foo,"),
        ("^foo", r"^foo\b"),
        ("^foo.*", r"^foo.*"),
    ],
)
def test_retouch_wake_up(wake_up: str, expect: str) -> None:
    assert retouch_wake_up(wake_up) == expect
