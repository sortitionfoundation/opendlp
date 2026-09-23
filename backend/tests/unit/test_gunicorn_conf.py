"""ABOUTME: Unit tests for the gunicorn.conf.py hooks at the repository root
ABOUTME: Verifies post_worker_init enables faulthandler so worker timeouts dump tracebacks"""

import faulthandler
import importlib.util
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

_CONF_PATH = Path(__file__).parents[2] / "gunicorn.conf.py"

# Mirrors the order gunicorn uses: init_process() installs a Python-level
# SIGABRT handler, and only then does the post_worker_init hook run. The
# script then aborts itself, so the dump (or its absence) is observable.
_ABORT_SCRIPT = f"""
import importlib.util, os, signal, sys

def gunicorn_handle_abort(sig, frame):
    print("PYTHON HANDLER RAN", file=sys.stderr)
    sys.exit(1)

signal.signal(signal.SIGABRT, gunicorn_handle_abort)

spec = importlib.util.spec_from_file_location("gunicorn_conf", {str(_CONF_PATH)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.post_worker_init(None)

def blocking_call():
    os.kill(os.getpid(), signal.SIGABRT)

blocking_call()
"""


@pytest.fixture
def gunicorn_conf() -> Iterator[ModuleType]:
    spec = importlib.util.spec_from_file_location("gunicorn_conf", _CONF_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    was_enabled = faulthandler.is_enabled()
    yield module
    # Restore whatever state the test session had before
    if not was_enabled:
        faulthandler.disable()


class TestGunicornConf:
    def test_post_worker_init_enables_faulthandler(self, gunicorn_conf: ModuleType) -> None:
        faulthandler.disable()

        gunicorn_conf.post_worker_init(MagicMock())

        assert faulthandler.is_enabled() is True

    def test_no_post_fork_hook(self, gunicorn_conf: ModuleType) -> None:
        # post_fork runs before gunicorn installs its own SIGABRT handler, so a
        # faulthandler enabled there is overridden - see the hook's docstring.
        assert not hasattr(gunicorn_conf, "post_fork")

    def test_abort_after_gunicorn_signal_setup_dumps_traceback(self) -> None:
        result = subprocess.run(  # noqa: S603 - fixed interpreter and script, no untrusted input
            [sys.executable, "-c", _ABORT_SCRIPT],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        assert "Fatal Python error: Aborted" in result.stderr
        assert "in blocking_call" in result.stderr  # the dumped stack names the blocking frame
        # faulthandler restores the previous handler before re-raising, so
        # gunicorn's abort handler still runs after the dump
        assert result.stderr.index("in blocking_call") < result.stderr.index("PYTHON HANDLER RAN")
        assert result.returncode == 1
