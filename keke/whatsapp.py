import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from time import sleep
from typing import Callable, NewType, Optional, cast

from selenium.common import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.wait import WebDriverWait

from keke.chat_client import ChatState
from keke.data_types import (
    KEKE_PREFIX,
    ChatMessage,
    GroupName,
    MessageContent,
    OpenAiMessage,
    Role,
)

logger = logging.getLogger(__name__)


WHATSAPP_WEB_URL = "https://web.whatsapp.com/"
XPATH_RECALLED_ICON = "span[@data-testid='recalled']"


def xpath_has_class(class_name: str) -> str:
    return f"contains(concat(' ', normalize-space(@class), ' '), ' {class_name} ')"


XPATH_MESSAGE_OUT = xpath_has_class("message-out")
XPATH_MESSAGE_IN = xpath_has_class("message-in")
XPATH_IS_NOT_RECALLED = f"not(descendant::{XPATH_RECALLED_ICON})"
XPATH_MESSAGES = (
    f"//div[({XPATH_MESSAGE_OUT} or {XPATH_MESSAGE_IN}) and {XPATH_IS_NOT_RECALLED}]"
)
XPATH_LAST_MESSAGE = f"({XPATH_MESSAGES})[last()]"
XPATH_LAST_MESSAGE_ID_ELEMENT = f"{XPATH_LAST_MESSAGE}/.."
XPATH_MESSAGE_FIELD = "//div[@data-testid='compose-box']//div[@contenteditable='true']"
XPATH_UNREAD_COUNT_ICON = "span[@data-testid='icon-unread-count']"
XPATH_GROUP_TITLE_ELEMENT = (
    "//div["
    "@data-testid='cell-frame-container' and "
    f"descendant::{XPATH_UNREAD_COUNT_ICON}"
    "]"
    "//div[@data-testid='cell-frame-title']/span[@title]"
)
XPATH_GROUP_CONTAINER = (
    "(@data-testid='cell-frame-container' or" " @data-testid='message-yourself-row')"
)
XPATH_GROUP_TITLE = "div[@data-testid='cell-frame-title']/span[@title]"
XPATH_TIME_UPDATED = "div[@data-testid='cell-frame-primary-detail']/span[{is_now}]"
XPATH_RECENT_GROUP_TITLE_ELEMENT = (
    f"//div[{XPATH_GROUP_CONTAINER} and descendant::{XPATH_TIME_UPDATED}]"
    f"//{XPATH_GROUP_TITLE}"
)


WhatsAppMessageId = NewType("WhatsAppMessageId", str)


@dataclass
class WhatsAppMessage(ChatMessage):
    msgid: WhatsAppMessageId
    author: str

    def to_dict(self) -> OpenAiMessage:
        """Return a dictionary representation of the message."""
        author = "" if self.is_from_keke else f"{self.author}: "
        return OpenAiMessage(
            role=Role("assistant" if self.is_from_keke else "user"),
            content=MessageContent(f"{author}{self.text_without_keke_prefix}"),
        )

    def __str__(self) -> str:
        """Return a string representation of the message."""
        author = "Keke" if self.is_from_keke else self.author
        return f"{self.timestamp:%H.%M} {author}: {self.text_without_keke_prefix}"

    @property
    def text_without_keke_prefix(self) -> str:
        return self.text[len(KEKE_PREFIX) :] if self.is_from_keke else self.text

    @property
    def is_from_keke(self) -> bool:
        """Return whether the message is from Keke."""
        return self.text.startswith(KEKE_PREFIX)


@dataclass
class WhatsAppChatState(ChatState):
    last_messages_by_group: dict[str, WhatsAppMessage] = field(default_factory=dict)


def read_whatsapp_messages(
    driver: WebDriver, state: WhatsAppChatState
) -> tuple[dict[GroupName, list[WhatsAppMessage]], WhatsAppChatState]:
    """Read new messages from the next group which has any.

    :param driver: The Selenium driver.
    :param state: Last returned state from this function.
    :return: The new messages for each group which had any.

    """
    result: dict[GroupName, list[WhatsAppMessage]] = {}
    last_messages = state.last_messages_by_group.copy()
    open_whatsapp(driver)
    while True:
        current_group = get_selected_group_title(driver)
        last_message_in_current_group = (
            last_messages.get(current_group, None) if current_group else None
        )
        try:
            logger.debug(
                f"Finding groups with new messages. Last message in {current_group} is"
                f" {last_message_in_current_group}."
            )
            groups_with_new_messages = WebDriverWait(
                driver, timeout=10.0, poll_frequency=1.0
            ).until(next_unread_groups(last_message_in_current_group))
            logger.debug(f"Found new messages in {groups_with_new_messages}.")
        except TimeoutException:
            groups_with_new_messages = []
        sleep_extra = 0.0
        for group_title in groups_with_new_messages:
            open_group(driver, group_title)
            messages = scrape_messages(driver)
            new_messages_in_group = None
            last_seen_message_in_group = last_messages.get(group_title, None)
            if last_seen_message_in_group:
                last_seen_position = [
                    position
                    for position, msg in enumerate(messages)
                    if msg.msgid == last_seen_message_in_group.msgid
                ]
                if last_seen_position:
                    # The last seen message is still in the group. Only scrape new
                    # messages after it.
                    new_messages_in_group = messages[last_seen_position[-1] + 1 :]
                    if not new_messages_in_group:
                        # No new messages in the group. If there are none in other
                        # groups either, add a little sleep to avoid constant polling
                        # during the next 1-2 minutes after the newest message.
                        sleep_extra = 2.0
                logger.debug(
                    "%s: %d messages scraped, last seen is at position %s",
                    group_title,
                    len(messages),
                    last_seen_position,
                )
            if new_messages_in_group is None:
                # The last seen message is no longer in the group, or we haven't seen
                # any messages from it yet. Scrape all messages whose timestamp is
                # on the same or later minute than the last seen message. Note that this
                # means that we may get duplicate messages from the same minute as the
                # last seen message, so those need to be filtered out by the caller.
                last_seen_timestamp = (
                    last_seen_message_in_group.timestamp
                    if last_seen_message_in_group
                    else datetime.min
                )
                new_messages_in_group = [
                    message
                    for message in messages
                    if message.timestamp >= last_seen_timestamp
                    and message not in result.get(group_title, [])
                ]
            if not new_messages_in_group:
                continue
            for message in new_messages_in_group:
                logger.debug(
                    "Scraped: [%s] %s: %s (%s)",
                    message.timestamp,
                    message.author,
                    message.text,
                    message.msgid,
                )
            result.setdefault(group_title, []).extend(new_messages_in_group)
            last_messages[group_title] = new_messages_in_group[-1]
        if not result:
            logging.debug("No new messages found. Waiting for new messages...")
            sleep(sleep_extra)
            continue
        logging.debug(
            "Read %s",
            ", ".join(
                f"{len(msgs)} messages from {grp}" for grp, msgs in result.items()
            ),
        )
        return result, WhatsAppChatState(last_messages)


def scrape_messages(driver: WebDriver) -> list[WhatsAppMessage]:
    """Scrape all messages from the currently open group.

    :param driver: The Selenium driver.
    :return: The scraped messages. Messages with no text are skipped.

    """
    result = []
    for el in find_messages(driver):
        try:
            result.append(scrape_message(el))
        except NoSuchElementException:
            continue
    return result


def scrape_message(element: WebElement) -> WhatsAppMessage:
    """Scrape a WhatsApp message from a ``.message-in`` or ``.message-out`` element.

    :param element: The ``.message-in`` or ``message-out`` element.
    :return: The scraped message.
    :raises NoSuchElementException: If the message has no text.

    """
    bubble = element.find_element(By.CSS_SELECTOR, "div.copyable-text")
    date_author = bubble.get_attribute("data-pre-plain-text").strip()
    assert date_author.startswith("[")
    assert date_author.endswith(":")
    date_str, author = date_author[1:-1].split("] ", 1)
    date = datetime.strptime(date_str, "%H.%M, %d.%m.%Y")
    text = MessageContent(
        bubble.find_element(By.CSS_SELECTOR, "span.selectable-text").text
    )
    msgid = WhatsAppMessageId(
        element.find_element(By.XPATH, "./..").get_attribute("data-id")
    )
    return WhatsAppMessage(timestamp=date, msgid=msgid, author=author, text=text)


def find_messages(driver: WebDriver) -> list[WebElement]:
    return driver.find_elements(By.CSS_SELECTOR, "div.message-out, div.message-in")


def get_last_message_id(driver: WebDriver) -> Optional[str]:
    try:
        last_message = driver.find_element(By.XPATH, XPATH_LAST_MESSAGE_ID_ELEMENT)
    except NoSuchElementException:
        return None
    return last_message.get_attribute("data-id")


def last_msgid_is_not(msgid: str) -> Callable[[WebDriver], bool]:
    def _msgid_not(driver: WebDriver) -> bool:
        return get_last_message_id(driver) != msgid

    return _msgid_not


def next_unread_groups(
    message: Optional[WhatsAppMessage],
) -> Callable[[WebDriver], list[GroupName]]:
    """Return a function that returns the title of the next group with unread messages.

    If there are no unread messages, return None.

    :message: The last message that was read in the current open group.

    """

    def _groups(driver: WebDriver) -> list[GroupName]:
        """Return the titles of groups with unread messages.

        If the current group has unread messages, include it as the first element in the
        list.

        :param driver: The Selenium driver.
        :return: The titles of groups with unread messages.

        """
        unread_groups = find_groups_with_unread(driver)
        message_id = message.msgid if message else None
        new_last_message_id = get_last_message_id(driver)
        if new_last_message_id != message_id:
            logger.debug(
                f"Last message ID changed from {message_id} to {new_last_message_id}."
            )
            current_group = get_selected_group_title(driver)
            if current_group and current_group not in unread_groups:
                return [current_group] + unread_groups
        return unread_groups

    return _groups


def open_whatsapp(driver: WebDriver) -> None:
    if driver.current_url != WHATSAPP_WEB_URL:
        driver.get(WHATSAPP_WEB_URL)


def open_group(driver: WebDriver, group: str) -> None:
    open_whatsapp(driver)
    if get_selected_group_title(driver) == group:
        return
    group_link = WebDriverWait(driver, 30).until(
        lambda d: d.find_element(By.XPATH, f"//span[@title='{group}']")
    )
    group_link.click()


def highlight(element: WebElement) -> None:
    """Highlights (blinks) a Selenium Webdriver element"""
    parent = element._parent

    def apply_style(s: str) -> None:
        parent.execute_script(
            "arguments[0].setAttribute('style', arguments[1]);", element, s
        )

    original_style = element.get_attribute("style")
    apply_style("background: yellow; border: 2px solid red;")
    sleep(0.3)
    apply_style(original_style)


def find_next_group_with_unread(driver: WebDriver) -> Optional[str]:
    """Return the title of the next group with unread messages.

    :param driver: The Selenium WebDriver.
    :return: The title of the next group with unread messages.

    """
    try:
        group = driver.find_element(By.XPATH, XPATH_GROUP_TITLE_ELEMENT)
    except NoSuchElementException:
        return None
    return group.get_attribute("title")


def find_groups_with_unread(driver: WebDriver) -> list[GroupName]:
    """Return a dictionary of groups with unread messages and their links.

    :param driver: The Selenium WebDriver.
    :return: A dictionary of group names and their links.

    """
    now = datetime.now()
    minute_ago = now - timedelta(minutes=1)
    xpath_is_now = " or ".join(f"text()='{t:%H.%M}'" for t in [now, minute_ago])
    xpath = XPATH_RECENT_GROUP_TITLE_ELEMENT.format(is_now=xpath_is_now)
    title_elements = driver.find_elements(By.XPATH, xpath)
    return [GroupName(el.get_attribute("title")) for el in title_elements]


def get_selected_group_title(driver: WebDriver) -> Optional[GroupName]:
    """Return the title of the currently selected group.

    :param driver: The Selenium WebDriver.
    :return: The title of the currently selected group, or None if no group is selected.

    """
    try:
        title_element = driver.find_element(
            By.XPATH,
            ".//div[@id='pane-side']"
            "//div[@role='row' and @aria-selected='true']"
            "//div[@data-testid='cell-frame-title']"
            "/span[@title]",
        )
    except NoSuchElementException:
        return None
    return cast(GroupName, title_element.get_attribute("title"))


def send_whatsapp_message(driver: WebDriver, group_title: GroupName, text: str) -> None:
    open_group(driver, group_title)
    message_field = driver.find_element(By.XPATH, XPATH_MESSAGE_FIELD)
    try:
        message_field.click()
    except WebDriverException:
        driver.save_screenshot(
            f"keke-{datetime.now():%Y-%m-%dT%H-%M-%S}"
            " compose box input not found.png"
        )
    for char in f"{KEKE_PREFIX}{text}":
        message_field.send_keys(char)
        sleep(0.01)
    message_field.send_keys(Keys.RETURN)
