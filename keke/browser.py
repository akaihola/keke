import json
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver

SESSION_JSON = Path("keke-selenium-session.json")


def create_driver() -> WebDriver:
    profile = webdriver.FirefoxProfile(  # type: ignore[no-untyped-call]
        "./firefox-profile"
    )
    driver = webdriver.Firefox(profile)
    return driver


def attach_to_driver() -> WebDriver:
    session = json.loads(SESSION_JSON.read_text())
    driver = attach_to_session(session["url"], session["session_id"])
    return driver


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
