from datetime import datetime
from time import sleep
from typing import Callable

from keke.data_types import KEKE_PREFIX, WhatsAppMessage
from selenium.common import NoSuchElementException, WebDriverException
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.wait import WebDriverWait

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


def open_whatsapp(driver: WebDriver) -> None:
    if driver.current_url != WHATSAPP_WEB_URL:
        driver.get(WHATSAPP_WEB_URL)


def open_group(driver: WebDriver, group: str) -> None:
    open_whatsapp(driver)
    group_link = WebDriverWait(driver, 30).until(
        lambda d: d.find_element(By.XPATH, f"//span[@title='{group}']")
    )
    group_link.click()


def find_groups_with_unread(driver: WebDriver) -> dict[str, WebElement]:
    """Return a dictionary of groups with unread messages and their links.

    :param driver: The Selenium WebDriver.
    :return: A dictionary of group names and their links.

    """
    counts = driver.find_elements(By.XPATH, "//span[@data-testid='icon-unread-count']")
    containers = [
        count.find_element(
            By.XPATH, "./ancestor::div[@data-testid='cell-frame-container']"
        )
        for count in counts
    ]
    titles = [
        container.find_element(
            By.XPATH, ".//div[@data-testid='cell-frame-title']/span[@title]"
        )
        for container in containers
    ]
    return {title.get_attribute("title"): title for title in titles}


def get_selected_group_title(driver: WebDriver) -> str:
    """Return the title of the currently selected group.

    :param driver: The Selenium WebDriver.
    :return: The title of the currently selected group.

    """
    return driver.find_element(
        By.XPATH,
        ".//div[@id='pane-side']"
        "//div[@role='row' and @aria-selected='true']"
        "//div[@data-testid='cell-frame-title']"
        "/span[@title]",
    ).get_attribute("title")


def send_message(driver: WebDriver, completion: str) -> None:
    message_field = driver.find_element(
        By.XPATH,
        "//div[@data-testid='compose-box']//div[@contenteditable='true']",
    )
    try:
        message_field.click()
    except WebDriverException:
        driver.save_screenshot(
            f"keke-{datetime.now():%Y-%m-%dT%H-%M-%S}"
            " compose box input not found.png"
        )
    for char in f"{KEKE_PREFIX}{completion}":
        message_field.send_keys(char)
        sleep(0.01)
    message_field.send_keys(Keys.RETURN)
