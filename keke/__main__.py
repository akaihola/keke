import json
import re
from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep
from typing import Any, Callable

from selenium import webdriver
from selenium.common import NoSuchElementException
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.wait import WebDriverWait

from keke import ai
from keke.data_types import KEKE_PREFIX, WhatsAppMessage

SESSION_JSON = Path("keke-selenium-session.json")
WHATSAPP_WEB_URL = "https://web.whatsapp.com/"


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


def attach_to_session(executor_url: str, session_id: str) -> webdriver.Remote:
    original_execute = WebDriver.execute

    def new_command_execute(  # type: ignore[misc]
        self: WebDriver,
        driver_command: str,
        params: dict = None,  # type: ignore[type-arg,assignment]
    ) -> dict[Any, Any]:
        if driver_command == "newSession":
            # Mock the response
            return {"success": 0, "value": None, "sessionId": session_id}
        else:
            return original_execute(self, driver_command, params)

    # Patch the function before creating the driver object
    WebDriver.execute = new_command_execute  # type: ignore[method-assign]
    driver = webdriver.Remote(command_executor=executor_url, desired_capabilities={})
    driver.session_id = session_id  # type: ignore[assignment]
    # Replace the patched function with original function
    WebDriver.execute = original_execute  # type: ignore[method-assign]
    return driver


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


def create_driver() -> WebDriver:
    profile = webdriver.FirefoxProfile(  # type: ignore[no-untyped-call]
        "/home/kaiant/prg/ai/keke/firefox-profile"
    )
    driver = webdriver.Firefox(profile)
    return driver


def attach_to_driver() -> WebDriver:
    session = json.loads(SESSION_JSON.read_text())
    driver = attach_to_session(session["url"], session["session_id"])
    return driver


def is_recent(message: WhatsAppMessage) -> bool:
    print(f"Comparing {message.timestamp} to {datetime.now() - timedelta(minutes=1)}")
    return datetime.now() - message.timestamp < timedelta(minutes=1)


def is_for_keke(message: WhatsAppMessage) -> bool:
    return message.text.lower().startswith("keke,")


def is_quit(message: WhatsAppMessage) -> bool:
    return message.text.lower().replace(" ", "").startswith("keke,kuole")


def read_messages(
    driver: WebDriver, previous_messages: list[WhatsAppMessage]
) -> list[WhatsAppMessage]:
    last_message_id = previous_messages[-1].msgid if previous_messages else ""
    WebDriverWait(driver, 31536000.0, 0.5).until(last_msgid_is_not(last_message_id))
    msg_elements = find_messages(driver)
    new_messages = []
    for msg in msg_elements:
        try:
            bubble = msg.find_element(By.CSS_SELECTOR, "div.copyable-text")
            date_author = bubble.get_attribute("data-pre-plain-text").strip()
            assert date_author.startswith("[")
            assert date_author.endswith(":")
            date_str, author = date_author[1:-1].split("] ", 1)
            date = datetime.strptime(date_str, "%H.%M, %d.%m.%Y")
            text = bubble.find_element(By.CSS_SELECTOR, "span.selectable-text").text
            msgid = msg.find_element(By.XPATH, "./..").get_attribute("data-id")
            message = WhatsAppMessage(
                timestamp=date, msgid=msgid, author=author, text=text
            )
            if message not in previous_messages:
                new_messages.append(message)
        except NoSuchElementException:
            # only attachment(s), no text
            pass
    return new_messages


def find_messages(driver: WebDriver) -> list[WebElement]:
    return driver.find_elements(By.CSS_SELECTOR, "div.message-out, div.message-in")


def get_message_count(driver: WebDriver) -> int:
    return len(find_messages(driver))


def more_messages_than(count: int) -> Callable[[WebDriver], bool]:
    def _more_messages_than(driver: WebDriver) -> bool:
        return get_message_count(driver) > count

    return _more_messages_than


def get_last_message_id(driver: WebDriver) -> str:
    messages = find_messages(driver)
    if not messages:
        return ""
    return messages[-1].find_element(By.XPATH, "./..").get_attribute("data-id")


def last_msgid_is_not(msgid: str) -> Callable[[WebDriver], bool]:
    def _msgid_not(driver: WebDriver) -> bool:
        return get_last_message_id(driver) != msgid

    return _msgid_not


def open_group(driver: WebDriver, group: str) -> None:
    if driver.current_url != WHATSAPP_WEB_URL:
        driver.get(WHATSAPP_WEB_URL)
    group_link = WebDriverWait(driver, 30).until(
        lambda d: d.find_element(By.XPATH, f"//span[@title='{group}']")
    )
    group_link.click()


if __name__ == "__main__":
    main()
