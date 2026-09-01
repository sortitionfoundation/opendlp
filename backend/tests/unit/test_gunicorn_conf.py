"""ABOUTME: Unit tests for the gunicorn.conf.py hooks at the repository root
ABOUTME: Verifies post_fork enables faulthandler so worker timeouts dump tracebacks"""

import faulthandler
import importlib.util
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

_CONF_PATH = Path(__file__).parents[2] / "gunicorn.conf.py"


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
    def test_post_fork_enables_faulthandler(self, gunicorn_conf: ModuleType) -> None:
        faulthandler.disable()

        gunicorn_conf.post_fork(MagicMock(), MagicMock())

        assert faulthandler.is_enabled() is True
