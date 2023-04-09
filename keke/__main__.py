import json
import logging
import pyperclip
import re
from argparse import Namespace
from datetime import datetime, timedelta
from typing import Collection, Sequence

from selenium.common import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from keke import ai
from keke.browser import SESSION_JSON, attach_to_driver, create_driver
from keke.command_line import parse_command_line
from keke.data_types import KEKE_PREFIX, ChatMessage, ChatName, WhatsAppMarkup
from keke.log import setup_logging
from keke.whatsapp import (
    WhatsAppChatState,
    WhatsAppMessage,
    WhatsAppMessageId,
    read_whatsapp_messages,
    send_whatsapp_message,
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Main entry point for the keke package."""
    args = parse_command_line(run_driver, run_with_firefox)
    setup_logging(args.log_level)
    if args.dump_config:
        logging.basicConfig(level=logging.INFO)
        logger.info("Dry run, no messages will be read or sent.")
        logger.info("==========================================")
        logger.info(f"Arguments:")
        for option, value in vars(args).items():
            logger.info(f"  {option}: {value}")
    args.func(args)


def run_driver(args: Namespace) -> None:
    """Run a browser, save the session info to a file, and close after user input.

    This is useful for debugging, as it allows you to attach to the browser session from
    another process.

    :param args: Command line arguments.

    """
    if args.dump_config:
        logger.info(f"Would run browser {'headless' if args.headless else 'visible'}.")
        logger.info("Would write browser session info into {SESSION_JSON}.")
        return
    driver = create_driver(headless=args.headless)
    session = {"url": driver.command_executor._url, "session_id": driver.session_id}
    SESSION_JSON.write_text(json.dumps(session))
    input("Press enter to close the browser")
    driver.close()


def run_with_firefox(args: Namespace) -> None:
    """Run the bot with Firefox.

    :param args: Command line arguments.

    """
    _ = pyperclip.paste()
    if args.use_open_driver:
        if args.dump_config:
            logger.info("Would attach to driver session from {SESSION_JSON}.")
            return
        driver = attach_to_driver()
    else:
        if args.dump_config:
            logger.info(
                f"Would create a {'headless' if args.headless else 'visible'} browser."
            )
            return
        driver = create_driver(headless=args.headless)
    try:
        participate_in_chat(driver, args.bundle, args.wake_up, args.dry_run)
    except WebDriverException as exc:
        driver.save_screenshot(
            f"keke-selenium-error-{datetime.now():%Y-%m-%dT%H-%M-%S}.png"
        )
        logger.exception(exc)
    if not args.use_open_driver:
        driver.close()


def participate_in_chat(
    driver: WebDriver,
    group_bundles: Collection[Sequence[ChatName]],
    wake_up: str,
    dry_run: bool,
) -> None:
    """Participate in the chat.

    Read new messages from groups, and send responses to the destination groups
    corresponding to the source groups of the messages as defined in group bundles,
    or the group itself if it is not part of any bundle.

    :param driver: The Selenium WebDriver.
    :param group_bundles: A list of groups whose messages should be merged into one
                          discussion and replied to in the first group of the bundle.
    :param wake_up: The wake-up regular expression to respond to.
    :param dry_run: ``True`` to prevent sending responses and print them on the
                    terminal.

    """
    all_messages: dict[ChatName, list[ChatMessage]] = {}
    whatsapp_state = WhatsAppChatState()
    while True:
        new_messages_in_groups, whatsapp_state = read_whatsapp_messages(
            driver, whatsapp_state
        )
        if not new_messages_in_groups:
            continue
        for source_group, new_messages in new_messages_in_groups.items():
            if not new_messages:
                continue
            destination_group = find_destination_group(source_group, group_bundles)
            group_messages = all_messages.setdefault(destination_group, [])
            # De-duplicate messages. In rare cases, a message may be read twice when
            # multiple messages appear on the same minute.
            unique_new_messages = [m for m in new_messages if m not in group_messages]
            if not unique_new_messages:
                continue
            group_messages.extend(unique_new_messages)
            logger.debug(
                "%d new scraped messages from %s had %d unique unseen messages, full"
                " length now %d messages",
                len(new_messages),
                source_group,
                len(unique_new_messages),
                len(group_messages),
            )
            last_message = unique_new_messages[-1]
            recent_new_messages = [
                m for m in unique_new_messages if is_recent(m) or m is last_message
            ]
            if any(is_for_keke(m, wake_up) for m in recent_new_messages):
                respond(driver, destination_group, group_messages, dry_run)
            if any(is_quit(m) for m in recent_new_messages):
                break


def respond(
    driver: WebDriver,
    chat_title: ChatName,
    group_messages: list[ChatMessage],
    dry_run: bool,
) -> None:
    """Respond to previously read messages in a group.

    :param driver: The Selenium WebDriver.
    :param chat_title: The group to send the response to.
    :param group_messages: The messages to respond to.
    :param dry_run: ``True`` to just print responses on the terminal

    """
    completion = WhatsAppMarkup(
        re.sub(
            pattern=r"^ \s* \*? Keke : \s*",
            repl="",
            string=ai.interact(chat_title, group_messages),
            flags=re.VERBOSE,
        )
    )
    if dry_run:
        logger.info(f"<{chat_title}> {KEKE_PREFIX}{completion}")
        now = datetime.utcnow()
        group_messages.append(
            WhatsAppMessage(
                now,
                completion,
                WhatsAppMessageId(str(now)),
                WhatsAppMessageId("dry-run"),
            )
        )
    else:
        send_whatsapp_message(driver, chat_title, completion)


def find_destination_group(
    group: ChatName, group_bundles: Collection[Sequence[ChatName]]
) -> ChatName:
    """Find the destination group for a source group.

    :param group: A group to search the destination group for.
    :param group_bundles: A list of groups whose messages should be merged into one
                          discussion and replied to in the first group of the bundle.
    :return: The destination group for the given group. This is the group itself if it
             is not part of any bundle or if it's the first group in a bundle.

    """
    for groups_in_bundle in group_bundles:
        if group in groups_in_bundle:
            return groups_in_bundle[0]
    return group


def is_recent(message: ChatMessage) -> bool:
    """Check if a message is recent (no older than 1 minute).

    :param message: The message to check.
    :return: ``True`` if the message is recent, ``False`` otherwise.

    """
    return datetime.now() - message.timestamp < timedelta(minutes=1)


def is_for_keke(message: ChatMessage, wake_up: str) -> bool:
    """Check if a message is for the chatbot.

    :param message: The message to check.
    :param wake_up: The wake-up regular expression to respond to.
    :return: ``True`` if the message is for the chatbot, ``False`` otherwise.

    """
    return bool(
        re.search(wake_up, message.text, re.IGNORECASE)
        and not message.text.startswith(KEKE_PREFIX)
    )


def is_quit(message: ChatMessage) -> bool:
    """Check if a message is a request to quit.

    :param message: The message to check.
    :return: ``True`` if the message is a request to quit, ``False`` otherwise.

    """
    return message.text.lower().replace(" ", "").startswith("keke,kuole")


if __name__ == "__main__":
    main()
