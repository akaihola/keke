import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from time import sleep
from typing import Callable, NewType, Optional, cast

from bs4 import BeautifulSoup
from keke.chat_client import ChatState
from keke.data_types import (
    KEKE_PREFIX,
    ChatMessage,
    ChatName,
    MessageContent,
    OpenAiMessage,
    Role,
)
from selenium.common import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.wait import WebDriverWait

logger = logging.getLogger(__name__)


def xpath_has_class(class_name: str) -> str:
    """Return an XPath predicate that matches an element with the given class name.

    :param class_name: The class name to match.
    :return: An XPath predicate.

    """
    return f"contains(concat(' ', normalize-space(@class), ' '), ' {class_name} ')"


WHATSAPP_WEB_URL = "https://web.whatsapp.com/"
XPATH_CHATLIST_HEADER = "//header[@data-testid='chatlist-header']"
XPATH_BUTTERBAR = "//span[@data-testid='chat-butterbar']/div"
XPATH_MESSAGE_OUT = xpath_has_class("message-out")
XPATH_MESSAGE_IN = xpath_has_class("message-in")
XPATH_RECALLED_ICON = "span[@data-testid='recalled']"
XPATH_IS_NOT_RECALLED = f"not(descendant::{XPATH_RECALLED_ICON})"
XPATH_MESSAGES = (
    f"//div[({XPATH_MESSAGE_OUT} or {XPATH_MESSAGE_IN}) and {XPATH_IS_NOT_RECALLED}]"
)
XPATH_LAST_MESSAGE = f"({XPATH_MESSAGES})[last()]"
XPATH_LAST_MESSAGE_ID_ELEMENT = f"{XPATH_LAST_MESSAGE}/.."
XPATH_MESSAGE_FIELD = "//div[@data-testid='compose-box']//div[@contenteditable='true']"
XPATH_CHAT_CONTAINER = (
    "(@data-testid='cell-frame-container' or @data-testid='message-yourself-row')"
)
XPATH_CHAT_TITLE = "div[@data-testid='cell-frame-title']/span[@title]"
XPATH_TIME_UPDATED = "div[@data-testid='cell-frame-primary-detail']/span[{is_now}]"
XPATH_RECENT_CHAT_TITLE_ELEMENT = (
    f"//div[{XPATH_CHAT_CONTAINER} and descendant::{XPATH_TIME_UPDATED}]"
    f"//{XPATH_CHAT_TITLE}"
)


WhatsAppMessageId = NewType("WhatsAppMessageId", str)


@dataclass
class WhatsAppMessage(ChatMessage):
    msgid: WhatsAppMessageId

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
    last_messages_by_chat: dict[str, WhatsAppMessage] = field(default_factory=dict)


def read_whatsapp_messages(
    driver: WebDriver, state: WhatsAppChatState
) -> tuple[dict[ChatName, list[WhatsAppMessage]], WhatsAppChatState]:
    """Read new messages from the next chat which has any.

    :param driver: The Selenium driver.
    :param state: Last returned state from this function.
    :return: The new messages for each chat which had any.

    """
    result: dict[ChatName, list[WhatsAppMessage]] = {}
    last_messages = state.last_messages_by_chat.copy()
    open_whatsapp(driver)
    while True:
        current_chat = get_selected_chat_title(driver)
        last_message_in_current_chat = (
            last_messages.get(current_chat, None) if current_chat else None
        )
        try:
            logger.debug(
                f"Finding chats with new messages. Last message in {current_chat} is"
                f" {last_message_in_current_chat}."
            )
            chats_with_new_messages = WebDriverWait(
                driver, timeout=10.0, poll_frequency=1.0
            ).until(next_unread_chats(last_message_in_current_chat))
            logger.debug(f"Found new messages in {chats_with_new_messages}.")
        except TimeoutException:
            chats_with_new_messages = []
        sleep_extra = 0.0
        for chat_title in chats_with_new_messages:
            open_chat(driver, chat_title)
            messages = scrape_messages(driver)
            new_messages_in_chat = None
            last_seen_message_in_chat = last_messages.get(chat_title, None)
            if last_seen_message_in_chat:
                last_seen_position = [
                    position
                    for position, msg in enumerate(messages)
                    if msg.msgid == last_seen_message_in_chat.msgid
                ]
                if last_seen_position:
                    # The last seen message is still in the chat. Only scrape new
                    # messages after it.
                    new_messages_in_chat = messages[last_seen_position[-1] + 1 :]
                    if not new_messages_in_chat:
                        # No new messages in the chat. If there are none in other
                        # chats either, add a little sleep to avoid constant polling
                        # during the next 1-2 minutes after the newest message.
                        sleep_extra = 2.0
                logger.debug(
                    "%s: %d messages scraped, last seen is at position %s",
                    chat_title,
                    len(messages),
                    last_seen_position,
                )
            if new_messages_in_chat is None:
                # The last seen message is no longer in the chat, or we haven't seen
                # any messages from it yet. Scrape all messages whose timestamp is
                # on the same or later minute than the last seen message. Note that this
                # means that we may get duplicate messages from the same minute as the
                # last seen message, so those need to be filtered out by the caller.
                last_seen_timestamp = (
                    last_seen_message_in_chat.timestamp
                    if last_seen_message_in_chat
                    else datetime.min
                )
                new_messages_in_chat = [
                    message
                    for message in messages
                    if message.timestamp >= last_seen_timestamp
                    and message not in result.get(chat_title, [])
                ]
            if not new_messages_in_chat:
                continue
            for message in new_messages_in_chat:
                logger.debug(
                    "Scraped: [%s] %s: %s (%s)",
                    message.timestamp,
                    message.author,
                    message.text,
                    message.msgid,
                )
            result.setdefault(chat_title, []).extend(new_messages_in_chat)
            last_messages[chat_title] = new_messages_in_chat[-1]
        if not result:
            logging.debug("No new messages found. Waiting for new messages...")
            sleep(sleep_extra)
            continue
        logging.debug(
            "Read %s",
            ", ".join(
                f"{len(msgs)} messages from {chat}" for chat, msgs in result.items()
            ),
        )
        return result, WhatsAppChatState(last_messages)


def scrape_messages(driver: WebDriver) -> list[WhatsAppMessage]:
    """Scrape all messages from the currently open chat.

    :param driver: The Selenium driver.
    :return: The scraped messages. Messages with no text are skipped.

    """
    result = []
    for el in driver.find_elements(By.XPATH, XPATH_MESSAGES):
        try:
            result.append(scrape_message(el))
        except NoSuchElementException:
            continue
    return result


def scrape_message(element: WebElement) -> WhatsAppMessage:
    """Scrape a WhatsApp message from a ``.message-in`` or ``.message-out`` element.

    .. note:: The message must have text. If it doesn't, a ``NoSuchElementException``
              is raised.

    :param element: The ``.message-in`` or ``message-out`` element.
    :return: The scraped message.
    :raises NoSuchElementException: If the message has no text.

    """
    bubble = element.find_element(By.CSS_SELECTOR, "div.copyable-text")
    date_author = bubble.get_attribute("data-pre-plain-text").strip()
    author, date = parse_author_and_date(date_author)
    msg_el = bubble.find_element(By.CSS_SELECTOR, f"span.selectable-text > span")
    msg_html = msg_el.get_attribute("outerHTML")
    text = unrender_message(msg_html)
    msgid = WhatsAppMessageId(
        element.find_element(By.XPATH, "./..").get_attribute("data-id")
    )
    return WhatsAppMessage(timestamp=date, msgid=msgid, author=author, text=text)


def unrender_message(msg_html: str) -> MessageContent:
    """Unrender a WhatsApp message from HTML back to WhatsApp markup.

    Bold text is converted to back to ``*bold*``.

    .. todo:: Add support for italics and other formatting supported by WhatApp.

    :param msg_html: The HTML code of the message from the WhatsApp UI.
    :return: The WhatsApp markup of the message.

    """
    message_soup = BeautifulSoup(msg_html, "html.parser")
    for strong in message_soup.find_all("strong"):
        strong.string = f"*{strong.string}*"
    text = MessageContent(message_soup.get_text())
    return text


def parse_author_and_date(date_author: str) -> tuple[str, datetime]:
    """Parse the author and date from a WhatsApp message bubble.

    Example ``date_author`` value: ``[12.34, 01.02.2021] Arthur Author:``

    .. todo:: The date format is probably dependent on the browser language. This now
              assumes that the browser is set to Finnish.

    :param date_author: The text in the ``data-pre-plain-text`` attribute of the
                        ``div.copyable-text`` element.
    :return: The author and date of the message.

    """
    assert date_author.startswith("[")
    assert date_author.endswith(":")
    date_str, author = date_author[1:-1].split("] ", 1)
    date = datetime.strptime(date_str, "%H.%M, %d.%m.%Y")
    return author, date


def get_last_message_id(driver: WebDriver) -> Optional[str]:
    """Return the ID of the last message in the currently open chat.

    :param driver: The Selenium driver.
    :return: The ID of the last message in the currently open chat, or ``None`` if there
             are no messages in the chat.

    """
    try:
        latest_message = driver.find_element(By.XPATH, XPATH_LAST_MESSAGE_ID_ELEMENT)
    except NoSuchElementException:
        return None
    return latest_message.get_attribute("data-id")


def next_unread_chats(
    latest_message: Optional[WhatsAppMessage],
) -> Callable[[WebDriver], list[ChatName]]:
    """Return a function that returns the title of the next chat with unread messages.

    If there are no unread messages, return None.

    :latest_message: The last message that was read in the current open chat.

    """

    def _chats(driver: WebDriver) -> list[ChatName]:
        """Return the titles of chats with unread messages.

        If the current chat has unread messages, include it as the first element in the
        list.

        :param driver: The Selenium driver.
        :return: The titles of chats with unread messages.

        """
        unread_chats = find_chats_with_unread(driver)
        message_id = latest_message.msgid if latest_message else None
        new_latest_message_id = get_last_message_id(driver)
        if new_latest_message_id != message_id:
            current_chat = get_selected_chat_title(driver)
            if current_chat and current_chat not in unread_chats:
                return [current_chat] + unread_chats
        return unread_chats

    return _chats


def open_whatsapp(driver: WebDriver) -> None:
    """Open WhatsApp Web if it is not already open.

    :param driver: The Selenium driver.

    """
    if driver.current_url == WHATSAPP_WEB_URL:
        return None
    driver.get(WHATSAPP_WEB_URL)
    logger.debug("Waiting for the chatlist-header to appear")
    WebDriverWait(driver, 60).until(
        lambda d: d.find_element(By.XPATH, XPATH_CHATLIST_HEADER)
    )
    logger.debug("Waiting for a moment in case the butterbar appears")
    try:
        butterbar = WebDriverWait(driver, 2).until(
            lambda d: d.find_element(By.XPATH, XPATH_BUTTERBAR)
        )
    except TimeoutException:
        return
    logger.debug("Clicking the butterbar, maybe this will update WhatsApp Web")
    # TODO: The butterbar may also notify about WhatsApp Web being open in another
    #       browser tab.
    butterbar.click()


def open_chat(driver: WebDriver, chat_title: str) -> None:
    """Open a WhatsApp chat.

    Open WhatsApp Web if it is not already open. If the chat is not already open, open
    it by clicking on the chat title in the left sidebar.

    :param driver: The Selenium driver.
    :param chat_title: The title of the chat to open.

    """
    open_whatsapp(driver)
    if get_selected_chat_title(driver) == chat_title:
        return
    chat_link = WebDriverWait(driver, 30).until(
        lambda d: d.find_element(By.XPATH, f"//span[@title='{chat_title}']")
    )
    chat_link.click()


def highlight(element: WebElement) -> None:
    """Highlights (blinks) a Selenium Webdriver element"""

    def apply_style(s: str) -> None:
        element._parent.execute_script(
            "arguments[0].setAttribute('style', arguments[1]);", element, s
        )

    original_style = element.get_attribute("style")
    apply_style("background: yellow; border: 2px solid red;")
    sleep(0.3)
    apply_style(original_style)


def find_chats_with_unread(driver: WebDriver) -> list[ChatName]:
    """Return a dictionary of chats with unread messages and their links.

    :param driver: The Selenium WebDriver.
    :return: A dictionary of chat names and their links.

    """
    now = datetime.now()
    minute_ago = now - timedelta(minutes=1)
    is_now_precidate = " or ".join(f"text()='{t:%H.%M}'" for t in [now, minute_ago])
    xpath = XPATH_RECENT_CHAT_TITLE_ELEMENT.format(is_now=is_now_precidate)
    title_elements = driver.find_elements(By.XPATH, xpath)
    return [ChatName(el.get_attribute("title")) for el in title_elements]


def get_selected_chat_title(driver: WebDriver) -> Optional[ChatName]:
    """Return the title of the currently selected chat.

    :param driver: The Selenium WebDriver.
    :return: The title of the currently selected chat. `None` if no chat is selected.

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
    return cast(ChatName, title_element.get_attribute("title"))


def send_whatsapp_message(driver: WebDriver, chat_title: ChatName, text: str) -> None:
    """Send a message to a WhatsApp chat.

    Open WhatsApp Web if it is not already open. Open the chat in the WhatsApp UI if
    it is not already open. Find the message field, click on it, and send the message
    at 100 characters/second, hitting ENTER and the end.

    :param driver: The Selenium WebDriver.
    :param chat_title: The title of the chat to send the message to.
    :param text: The text of the message to send.

    """
    open_chat(driver, chat_title)
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
