import logging
from typing import Any

from celery import Celery, Task
from celery.signals import worker_process_init

from opendlp import bootstrap, config


def get_celery_app(redis_host: str = "", redis_port: int = 0, old_app: Celery | None = None) -> Celery:
    # Configure Celery (using Redis as both broker and result backend)
    redis_cfg = config.RedisCfg.from_env()
    if redis_host:
        redis_cfg.host = redis_host
    if redis_port:
        redis_cfg.port = redis_port
    # only re-initialise if the URL has changed
    if old_app and old_app.conf.broker_write_url == redis_cfg.to_url():
        return old_app
    app = Celery(
        "opendlp",
        broker=redis_cfg.to_url(),
        backend=redis_cfg.to_url(),
    )
    app.conf.update(
        timezone="UTC",
        # use pickle across the board, so we can use rich objects, not just JSON
        event_serializer="pickle",
        task_serializer="pickle",
        result_serializer="pickle",
        accept_content=["application/json", "application/x-python-serialize"],
        # track when tasks are started
        task_track_started=True,
        # Configure periodic tasks (Celery Beat schedule)
        beat_schedule={
            "cleanup-old-password-reset-tokens": {
                "task": "opendlp.entrypoints.celery.tasks.cleanup_old_password_reset_tokens",
                "schedule": 3600.0,  # hourly
            },
            "cleanup-orphaned-tasks": {
                "task": "opendlp.entrypoints.celery.tasks.cleanup_orphaned_tasks",
                "schedule": 300.0,  # Run every 5 minutes (300 seconds)
            },
            "monitor-selection": {
                "task": "opendlp.entrypoints.celery.tasks.monitor_selection_periodic",
                "schedule": 3600.0,  # hourly
            },
            "prune-monitor-runs": {
                "task": "opendlp.entrypoints.celery.tasks.prune_monitor_run_records",
                "schedule": 86400.0,  # daily
            },
        },
    )

    return app


def reset_celery_app() -> None:
    """
    Used by tests to force resetting the app module attribute, so it is
    re-initialised from the current environment variables
    """
    global app
    app = get_celery_app(old_app=app)


app = get_celery_app()


@worker_process_init.connect
def reset_db_connections_after_fork(**_: Any) -> None:
    """Drop any SQLAlchemy engines inherited from the parent celery process.

    With the default prefork pool each worker is forked from the master.
    Any engine the master built before forking would have its file
    descriptors shared by every child, so concurrent queries from
    different workers would corrupt each other's TCP traffic.
    """
    bootstrap.dispose_cached_engines()


class CeleryContextHandler(logging.Handler):
    """
    A logger that sends the log messages through Celery to the AsyncResult
    object.
    """

    def __init__(self, context: Task) -> None:
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
