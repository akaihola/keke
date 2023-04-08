import logging
import re
from argparse import Action, ArgumentParser, Namespace
from typing import Any, Callable, List, Optional, Sequence, Union


class LogLevelAction(Action):  # pylint: disable=too-few-public-methods
    """Support for command line actions which increment/decrement the log level"""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        option_strings: List[str],
        dest: str,
        const: int,
        default: int = logging.WARNING,
        required: bool = False,
        help: Optional[str] = None,  # pylint: disable=redefined-builtin
        metavar: Optional[str] = None,
    ):
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=0,
            const=const,
            default=default,
            required=required,
            help=help,
            metavar=metavar,
        )

    def __call__(  # type: ignore[misc]
        self,
        parser: ArgumentParser,
        namespace: Namespace,
        values: Union[str, Sequence[Any], None],
        option_string: Optional[str] = None,
    ) -> None:
        current_level = getattr(namespace, self.dest, self.default)
        new_level = current_level + self.const
        new_level = max(new_level, logging.DEBUG)
        new_level = min(new_level, logging.CRITICAL)
        setattr(namespace, self.dest, new_level)


def retouch_wake_up(wake_up: str) -> str:
    """Add word boundaries to the wake-up string.

    :param wake_up: Wake-up string.
    :return: Wake-up string with word boundaries.

    """
    if re.match(r"\w", wake_up):
        wake_up = rf"\b{wake_up}"
    if re.search(r"\w$", wake_up):
        wake_up = rf"{wake_up}\b"
    return wake_up


def parse_command_line(
    run_driver: Callable[[Namespace], None],
    run_with_firefox: Callable[[Namespace], None],
) -> Namespace:
    """Parse command line arguments.

    :param run_driver: Function to run a browser and save the session.
    :param run_with_firefox: Function to run the chatbot with a newly created or an
                             existing browser.
    :return: Parsed command line options.

    """
    parser = ArgumentParser()
    parser.register("action", "log_level", LogLevelAction)
    parser.set_defaults(func=lambda _: parser.print_help())
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--dump-config", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "-v",
        "--verbose",
        action="log_level",
        dest="log_level",
        const=-10,
    )
    parser.add_argument("-q", "--quiet", action="log_level", dest="log_level", const=10)
    subparsers = parser.add_subparsers()
    parser_run_driver = subparsers.add_parser("run-driver")
    parser_run_driver.set_defaults(func=run_driver)
    parser_run = subparsers.add_parser("run")
    parser_run.add_argument(
        "--bundle",
        action="append",
        type=lambda s: [g.strip() for g in s.split(",")],
        default=[],
    )
    parser_run.add_argument("--use-open-driver", action="store_true")
    parser_run.add_argument(
        "--wake-up",
        default=r"^keke,",
        type=retouch_wake_up,
    )
    parser_run.set_defaults(func=run_with_firefox)
    args = parser.parse_args()
    return args
