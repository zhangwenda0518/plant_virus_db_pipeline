import logging

from neblab_rag.logging_config import configure_logging, get_logger


def test_get_logger_returns_bound_logger(caplog):
    configure_logging(level="DEBUG")
    log = get_logger("test")
    with caplog.at_level(logging.DEBUG):
        log.info("hello", key="value")
    assert "hello" in caplog.text
