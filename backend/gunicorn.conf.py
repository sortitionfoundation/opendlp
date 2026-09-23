# ABOUTME: Gunicorn configuration, auto-loaded from the working directory (./gunicorn.conf.py).
# ABOUTME: Makes worker timeouts diagnosable by dumping Python tracebacks on SIGABRT.

import faulthandler
from typing import Any


def post_worker_init(worker: Any) -> None:
    """Arrange for a traceback dump when the arbiter times out this worker.

    On worker timeout the arbiter sends SIGABRT, then SIGKILL if the worker
    does not exit. faulthandler.enable() installs a C-level SIGABRT handler
    that dumps every thread's Python stack to stderr, so the dump happens
    even when the worker is blocked inside a C extension (e.g. libpq waiting
    on the database) where Python-level signal handlers never get to run.

    After the dump faulthandler restores the previously installed handler
    and re-raises the signal, so gunicorn's own Python-level abort handler
    still runs afterwards and the worker exits the way it would have without
    faulthandler - the dump is purely additive.

    This must be the post_worker_init hook, not post_fork. The worker's
    init_process() runs between the two and installs gunicorn's own
    Python-level SIGABRT handler via signal.signal(), which replaces any
    handler installed earlier - so faulthandler enabled in post_fork is
    silently overridden and a timed-out worker dumps nothing.
    """
    faulthandler.enable()
