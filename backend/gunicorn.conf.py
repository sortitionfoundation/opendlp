# ABOUTME: Gunicorn configuration, auto-loaded from the working directory (./gunicorn.conf.py).
# ABOUTME: Makes worker timeouts diagnosable by dumping Python tracebacks on SIGABRT.

import faulthandler
from typing import Any


def post_fork(server: Any, worker: Any) -> None:
    """Arrange for a traceback dump when the arbiter times out this worker.

    On worker timeout the arbiter sends SIGABRT, then SIGKILL if the worker
    does not exit. faulthandler.enable() installs a C-level SIGABRT handler
    that dumps every thread's Python stack to stderr, so the dump happens
    even when the worker is blocked inside a C extension (e.g. libpq waiting
    on the database) where Python-level signal handlers never get to run.

    faulthandler then re-raises the signal with the default action, so the
    worker dies right after the dump instead of attempting a graceful exit -
    an acceptable trade for always knowing where it was stuck. (SIGABRT is a
    faulthandler "fault" signal, so register(..., chain=True) is not allowed
    for it and gunicorn's own Python-level abort handler cannot be kept.)
    """
    faulthandler.enable()
