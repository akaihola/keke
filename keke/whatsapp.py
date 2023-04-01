from typing import Callable

from datetime import datetime
from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.wait import WebDriverWait

from keke.data_types import WhatsAppMessage

WHATSAPP_WEB_URL = "https://web.whatsapp.com/"


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
