import logging.config
import os
from datetime import timedelta
from typing import TYPE_CHECKING

import structlog

from opendlp import config

if TYPE_CHECKING:
    try:
        import gunicorn.config
        import gunicorn.http
        import gunicorn.http.wsgi
    except ImportError:
        pass

timestamper = structlog.processors.TimeStamper(fmt="iso")
pre_chain = [
    # Add the log level and a timestamp to the event_dict if the log entry is not from structlog.
    structlog.stdlib.add_log_level,
    timestamper,
]

# switch to dev_console for development set up
handler_to_use = "dev_console" if config.is_development() else "default"

# Configure Python's standard logging with structlog integration
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processor": structlog.dev.ConsoleRenderer(colors=False),
            "foreign_pre_chain": pre_chain,
        },
        "json": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processor": structlog.processors.JSONRenderer(),
            "foreign_pre_chain": pre_chain,
        },
    },
    "handlers": {
        "default": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
        "dev_console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
    },
    "loggers": {
        "": {
            "handlers": [handler_to_use],
            "level": "INFO",
            "propagate": True,
        },
    },
})

# Configure structlog to work with stdlib logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)


def logging_setup(log_level: int = logging.INFO) -> None:
    default_handler = logging.getHandlerByName("default")
    assert default_handler is not None
    default_handler.setLevel(log_level)

    default_logger = logging.getLogger()
    default_logger.setLevel(log_level)

    if config.should_log_all_requests():
        logging.getLogger().setLevel(logging.DEBUG)
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True


class GunicornLogger:
    """
    Modified from: https://gist.github.com/airhorns/c2d34b2c823541fc0b32e5c853aab7e7
    A stripped down version of https://github.com/benoitc/gunicorn/blob/master/gunicorn/glogging.py to provide structlog logging in gunicorn
    Modified from http://stevetarver.github.io/2017/05/10/python-falcon-logging.html
    """

    def __init__(self, cfg: "gunicorn.config.Config") -> None:
        log_level = config.get_log_level()
        self._error_logger = structlog.get_logger("gunicorn.error")
        self._error_logger.setLevel(log_level)
        self._access_logger = structlog.get_logger("gunicorn.access")
        self._access_logger.setLevel(log_level)
        self.cfg = cfg

    def critical(self, msg: object, *args: object, **kwargs: object) -> None:
        self._error_logger.error(msg, *args, **kwargs)

    def error(self, msg: object, *args: object, **kwargs: object) -> None:
        self._error_logger.error(msg, *args, **kwargs)

    def warning(self, msg: object, *args: object, **kwargs: object) -> None:
        self._error_logger.warning(msg, *args, **kwargs)

    def info(self, msg: object, *args: object, **kwargs: object) -> None:
        self._error_logger.info(msg, *args, **kwargs)

    def debug(self, msg: object, *args: object, **kwargs: object) -> None:
        self._error_logger.debug(msg, *args, **kwargs)

    def exception(self, msg: object, *args: object, **kwargs: object) -> None:
        self._error_logger.exception(msg, *args, **kwargs)

    def log(self, lvl: int, msg: object, *args: object, **kwargs: object) -> None:
        self._error_logger.log(lvl, msg, *args, **kwargs)

    def access(
        self,
        resp: "gunicorn.http.wsgi.Response",
        req: "gunicorn.http.Request",
        environ: dict[str, object],
        request_time: timedelta,
    ) -> None:
        status = resp.status
        if isinstance(status, str):
            status = status.split(None, 1)[0]

        self._access_logger.info(
            "request",
            method=environ["REQUEST_METHOD"],
            request_uri=environ["RAW_URI"],
            status=status,
            response_length=getattr(resp, "sent", None),
            request_time_seconds=f"{request_time.seconds:d}.{request_time.microseconds:06d}",
            pid=f"<{os.getpid()}>",
        )

    def reopen_files(self) -> None:
        pass  # we don't support files

    def close_on_exec(self) -> None:
        pass  # we don't support files
