import logging

from celery import Celery, Task

from opendlp import config


def get_celery_app(redis_host: str = "", redis_port: int = 0) -> Celery:  # type: ignore[no-any-unimported]
    # Configure Celery (using Redis as both broker and result backend)
    redis_cfg = config.RedisCfg.from_env()
    if redis_host:
        redis_cfg.host = redis_host
    if redis_port:
        redis_cfg.port = redis_port
    redis_cfg.db = "0"
    app = Celery(
        "opendlp",
        broker=redis_cfg.to_url(),
        backend=redis_cfg.to_url(),
    )
    # use pickle across the board, so we can use rich objects, not just JSON
    app.conf.event_serializer = "pickle"  # this event_serializer is optional.
    app.conf.task_serializer = "pickle"
    app.conf.result_serializer = "pickle"
    app.conf.accept_content = ["application/json", "application/x-python-serialize"]
    return app


app = get_celery_app()


class CeleryContextHandler(logging.Handler):
    """
    A logger that sends the log messages through Celery to the AsyncResult
    object.
    """

    def __init__(self, context: Task) -> None:  # type: ignore[no-any-unimported]
        super().__init__()
        self.context = context
        self.messages: list[str] = []
        self.setFormatter(logging.Formatter(fmt="'%(asctime)s - %(levelname)s - %(message)s'"))

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self.messages.append(msg)
        self.context.update_state(
            state="PROGRESS",
            meta={"new_status_message": msg, "all_messages": self.messages},
        )
