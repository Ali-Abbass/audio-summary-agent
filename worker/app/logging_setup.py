from __future__ import annotations

import atexit
import logging
import logging.handlers
import queue
import sys
from copy import copy
from typing import Any

import structlog

_listener: logging.handlers.QueueListener | None = None
_configured = False


class PreservingQueueHandler(logging.handlers.QueueHandler):
    """Keep structured log records intact for ProcessorFormatter in listener thread."""

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        return copy(record)


def configure_logging(service: str, level: str = "INFO") -> None:
    global _configured, _listener
    if _configured:
        return

    log_queue: queue.SimpleQueue[Any] = queue.SimpleQueue()

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level.upper())
    root_logger.addHandler(PreservingQueueHandler(log_queue))

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
        ],
    )

    sink = logging.StreamHandler(sys.stdout)
    sink.setFormatter(formatter)

    _listener = logging.handlers.QueueListener(log_queue, sink, respect_handler_level=True)
    _listener.start()
    atexit.register(_listener.stop)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                ]
            ),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    structlog.contextvars.bind_contextvars(service=service)
    _configured = True
