import json
from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep
from typing import Callable

from selenium import webdriver
from selenium.common import NoSuchElementException
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.wait import WebDriverWait


SESSION_JSON = Path("keke-selenium-session.json")
WHATSAPP_WEB_URL = "https://web.whatsapp.com/"


def main():
    parser = ArgumentParser()
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
    profile = webdriver.FirefoxProfile("/home/kaiant/prg/ai/keke/firefox-profile")
    driver = webdriver.Firefox(profile)
    session = {"url": driver.command_executor._url, "session_id": driver.session_id}
    SESSION_JSON.write_text(json.dumps(session))
    input("Press enter to close the browser")
    driver.close()


def attach_to_session(executor_url, session_id):
    original_execute = WebDriver.execute

    def new_command_execute(self, command, params=None):
        if command == "newSession":
            # Mock the response
            return {"success": 0, "value": None, "sessionId": session_id}
        else:
            return original_execute(self, command, params)

    # Patch the function before creating the driver object
    WebDriver.execute = new_command_execute
    driver = webdriver.Remote(command_executor=executor_url, desired_capabilities={})
    driver.session_id = session_id
    # Replace the patched function with original function
    WebDriver.execute = original_execute
    return driver


def run_with_firefox(args: Namespace) -> None:
    if args.use_open_driver:
        session = json.loads(SESSION_JSON.read_text())
        driver = attach_to_session(session["url"], session["session_id"])
    else:
        profile = webdriver.FirefoxProfile("/home/kaiant/prg/ai/keke/firefox-profile")
        driver = webdriver.Firefox(profile)
    open_group(driver, args.group)
    count = 0
    all_messages = []
    while True:
        count, new_messages = read_messages(driver, all_messages, previous_count=count)
        for message in new_messages:
            print(message)
            all_messages.append(message)
            if is_for_keke(message) and is_recent(message):
                message_field = driver.find_element(
                    By.XPATH, "//div[@title='Kirjoita viesti']"
                )
                message_field.click()
                for char in "Keke: Kuulen.":
                    message_field.send_keys(char)
                    sleep(0.01)
                message_field.send_keys(Keys.RETURN)
    if not args.use_open_driver:
        driver.close()


def is_recent(message: dict) -> bool:
    return datetime.now() - message["date"] < timedelta(minutes=1)


def is_for_keke(message: dict) -> bool:
    return message["text"].lower().startswith("keke,")


def read_messages(
    driver: WebDriver, previous_messages: list[dict], previous_count: int
):
    WebDriverWait(driver, 31536000.0, 0.5).until(more_messages_than(previous_count))
    msgs = find_messages(driver)
    new_messages = []
    for msg in msgs:
        try:
            bubble = msg.find_element(By.CSS_SELECTOR, "div.copyable-text")
            date_author = bubble.get_attribute("data-pre-plain-text").strip()
            assert date_author.startswith("[")
            assert date_author.endswith(":")
            date_str, author = date_author[1:-1].split("] ", 1)
            date = datetime.strptime(date_str, "%H.%M, %d.%m.%Y")
            text = bubble.find_element(By.CSS_SELECTOR, "span.selectable-text").text
            message = {"date": date, "author": author, "text": text}
            if message not in previous_messages:
                new_messages.append(message)
        except NoSuchElementException:
            # only attachment(s), no text
            print(msg)
    return len(msgs), new_messages


def find_messages(driver: WebDriver):
    return driver.find_elements(By.CSS_SELECTOR, "div.message-out, div.message-in")


def get_message_count(driver: WebDriver) -> int:
    return len(find_messages(driver))


def more_messages_than(count: int) -> Callable[[WebDriver], bool]:
    def _more_messages_than(driver: WebDriver) -> bool:
        return get_message_count(driver) > count

    return _more_messages_than


def open_group(driver, group: str) -> None:
    if driver.current_url != WHATSAPP_WEB_URL:
        driver.get(WHATSAPP_WEB_URL)
    group_link = WebDriverWait(driver, 30).until(
        lambda d: d.find_element(By.XPATH, f"//span[@title='{group}']")
    )
    group_link.click()


if __name__ == "__main__":
    main()
