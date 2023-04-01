import json
import re
from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta
from time import sleep

from selenium.webdriver import Keys
from selenium.webdriver.common.by import By

from keke import ai
from keke.browser import SESSION_JSON, attach_to_driver, create_driver
from keke.data_types import KEKE_PREFIX, WhatsAppMessage
from keke.whatsapp import open_group, read_messages


def main() -> None:
    parser = ArgumentParser()
    parser.set_defaults(func=lambda _: parser.print_help())
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
    driver = create_driver()
    session = {"url": driver.command_executor._url, "session_id": driver.session_id}
    SESSION_JSON.write_text(json.dumps(session))
    input("Press enter to close the browser")
    driver.close()


def run_with_firefox(args: Namespace) -> None:
    if args.use_open_driver:
        driver = attach_to_driver()
    else:
        driver = create_driver()
    open_group(driver, args.group)
    all_messages: list[WhatsAppMessage] = []
    quit_ = False
    while True:
        if quit_:
            break
        new_messages = read_messages(driver, all_messages)
        for message in new_messages:
            print(message)
            all_messages.append(message)
            if is_for_keke(message) and is_recent(message):
                if is_quit(message):
                    quit_ = True
                    break
                completion = re.sub(
                    pattern=r"^ \s* \*? Keke : \s*",
                    repl="",
                    string=ai.interact(all_messages),
                    flags=re.VERBOSE,
                )
                message_field = driver.find_element(
                    By.XPATH, "//div[@title='Kirjoita viesti']"
                )
                message_field.click()
                for char in f"{KEKE_PREFIX}{completion}":
                    message_field.send_keys(char)
                    sleep(0.01)
                message_field.send_keys(Keys.RETURN)
    if not args.use_open_driver:
        driver.close()


def is_recent(message: WhatsAppMessage) -> bool:
    print(f"Comparing {message.timestamp} to {datetime.now() - timedelta(minutes=1)}")
    return datetime.now() - message.timestamp < timedelta(minutes=1)


def is_for_keke(message: WhatsAppMessage) -> bool:
    return message.text.lower().startswith("keke,")


def is_quit(message: WhatsAppMessage) -> bool:
    return message.text.lower().replace(" ", "").startswith("keke,kuole")


if __name__ == "__main__":
    main()
