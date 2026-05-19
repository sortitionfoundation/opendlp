"""ABOUTME: Integration tests for the `opendlp monitor` CLI subgroup
ABOUTME: Patches run_monitoring_selection to drive each branch of run-selection"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from opendlp.adapters.database import start_mappers
from opendlp.entrypoints.cli import cli
from opendlp.service_layer.monitoring import MonitorResult


@pytest.fixture(autouse=True)
def setup_mappers():
    start_mappers()


class TestMonitorRunSelectionCli:
    def test_success_exits_zero_and_prints_view_url(self, cli_with_session_factory):
        result_obj = MonitorResult(
            success=True,
            task_id=uuid.uuid4(),
            duration_seconds=12.3,
            message="ok",
            run_url="https://example.org/assembly/abc/selection/def",
        )
        with patch(
            "opendlp.entrypoints.cli.monitor.run_monitoring_selection",
            return_value=result_obj,
        ):
            result = cli_with_session_factory(cli, ["monitor", "run-selection"])

        assert result.exit_code == 0, result.output
        assert "✓" in result.output
        assert "View: https://example.org/assembly/abc/selection/def" in result.output

    def test_failure_default_strict_exits_one(self, cli_with_session_factory):
        result_obj = MonitorResult(
            success=False,
            task_id=uuid.uuid4(),
            message="boom",
            error="Traceback line",
        )
        with patch(
            "opendlp.entrypoints.cli.monitor.run_monitoring_selection",
            return_value=result_obj,
        ):
            result = cli_with_session_factory(cli, ["monitor", "run-selection"])

        assert result.exit_code == 1
        assert "✗" in result.output
        assert "Traceback line" in result.output

    def test_failure_no_strict_exits_zero(self, cli_with_session_factory):
        result_obj = MonitorResult(
            success=False,
            task_id=uuid.uuid4(),
            message="boom",
        )
        with patch(
            "opendlp.entrypoints.cli.monitor.run_monitoring_selection",
            return_value=result_obj,
        ):
            result = cli_with_session_factory(cli, ["monitor", "run-selection", "--no-strict"])

        assert result.exit_code == 0, result.output
        assert "✗" in result.output

    def test_not_configured_exits_zero_with_warning(self, cli_with_session_factory):
        result_obj = MonitorResult(
            success=False,
            not_configured=True,
            message="monitoring not configured",
        )
        with patch(
            "opendlp.entrypoints.cli.monitor.run_monitoring_selection",
            return_value=result_obj,
        ):
            result = cli_with_session_factory(cli, ["monitor", "run-selection"])

        assert result.exit_code == 0, result.output
        assert "⚠" in result.output
