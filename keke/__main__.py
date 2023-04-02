import json
import logging
import re
from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta

from keke import ai
from keke.browser import SESSION_JSON, attach_to_driver, create_driver
from keke.data_types import WhatsAppMessage
from keke.whatsapp import open_group, read_messages, send_message
from selenium.common import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

logger = logging.getLogger(__name__)


def main() -> None:
    parser = ArgumentParser()
    parser.set_defaults(func=lambda _: parser.print_help())
    parser.add_argument("--headless", action="store_true")
    subparsers = parser.add_subparsers()

    parser_run_driver = subparsers.add_parser("run-driver")
    parser_run_driver.set_defaults(func=run_driver)

    parser_run = subparsers.add_parser("run")
    parser_run.add_argument("--group", default="Kotiväki")
    parser_run.add_argument("--use-open-driver", action="store_true")
    parser_run.set_defaults(func=run_with_firefox)

    args = parser.parse_args()
    args.func(args)


def run_driver(args: Namespace) -> None:
    driver = create_driver(headless=args.headless)
    session = {"url": driver.command_executor._url, "session_id": driver.session_id}
    SESSION_JSON.write_text(json.dumps(session))
    input("Press enter to close the browser")
    driver.close()


def run_with_firefox(args: Namespace) -> None:
    if args.use_open_driver:
        driver = attach_to_driver()
    else:
        driver = create_driver(headless=args.headless)
    try:
        participate_in_chat(driver, args)
    except WebDriverException as exc:
        driver.save_screenshot(
            "keke-selenium-error-{datetime.now():%Y-%m-%dT%H-%M-%S}.png"
        )
        logger.error(exc)
    if not args.use_open_driver:
        driver.close()


def participate_in_chat(driver: WebDriver, args: Namespace) -> None:
    open_group(driver, args.group)
    all_messages: list[WhatsAppMessage] = []
    while True:
        new_messages = read_messages(driver, all_messages)
        if not new_messages:
            continue
        all_messages.extend(new_messages)
        last_message = new_messages[-1]
        recent_messages = [m for m in new_messages if is_recent(m) or m is last_message]
        respond = any(is_for_keke(m) for m in recent_messages)
        quit_ = any(is_quit(m) for m in recent_messages)
        if respond:
            completion = re.sub(
                pattern=r"^ \s* \*? Keke : \s*",
                repl="",
                string=ai.interact(all_messages),
                flags=re.VERBOSE,
            )
            send_message(driver, completion)
        if quit_:
            break


def is_recent(message: WhatsAppMessage) -> bool:
    return datetime.now() - message.timestamp < timedelta(minutes=1)


def is_for_keke(message: WhatsAppMessage) -> bool:
    return message.text.lower().startswith("keke,")


def is_quit(message: WhatsAppMessage) -> bool:
    return message.text.lower().replace(" ", "").startswith("keke,kuole")


if __name__ == "__main__":
    main()
