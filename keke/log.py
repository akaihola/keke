import logging


def setup_logging(log_level: int) -> None:
    """Set up logging with the given log level and a custom format string."""
    logging.basicConfig(level=log_level)
    if log_level == logging.INFO:
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        logging.getLogger().handlers[0].setFormatter(formatter)
    logging.getLogger("selenium.webdriver.remote.remote_connection").setLevel(
        logging.ERROR
    )
    logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
    logging.getLogger("urllib3.util.retry").setLevel(logging.ERROR)
    logging.getLogger("openai").setLevel(logging.ERROR)
