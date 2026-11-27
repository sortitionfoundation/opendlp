"""ABOUTME: Unit tests for CeleryTaskRunner, the TaskRunner adapter over Celery
ABOUTME: The one test file that reaches the real Celery boundary; it patches apply_async, AsyncResult and revoke"""

import uuid
from unittest.mock import Mock, patch

import pytest
from sortition_algorithms.settings import Settings

from opendlp.entrypoints.celery import tasks
from opendlp.entrypoints.celery.app import app
from opendlp.entrypoints.celery.runner import CeleryTaskRunner
from opendlp.service_layer.task_runner import TaskStatus


def _settings() -> Settings:
    return Settings(id_column="id", columns_to_keep=[])


class _Unpicklable:
    def __init__(self) -> None:
        self.callback = lambda: None


@pytest.fixture
def runner() -> CeleryTaskRunner:
    return CeleryTaskRunner()


class TestTaskMethodsPrepareWithoutSending:
    def test_nothing_is_published_until_the_dispatch_is_called(self, runner):
        task_id = uuid.uuid4()

        with patch.object(tasks.run_select_from_db, "apply_async") as apply_async:
            dispatch = runner.run_select_from_db(
                task_id=task_id,
                assembly_id=uuid.uuid4(),
                number_people_wanted=5,
                settings=_settings(),
                test_selection=False,
            )
            apply_async.assert_not_called()
            dispatch()

        apply_async.assert_called_once()

    def test_an_argument_that_cannot_be_pickled_raises_when_prepared(self, runner):
        with patch.object(tasks.load_gsheet, "apply_async") as apply_async, pytest.raises(Exception):  # noqa: B017
            runner.load_gsheet(task_id=uuid.uuid4(), data_source=_Unpicklable(), settings=_settings())  # type: ignore[arg-type]

        apply_async.assert_not_called()


class TestWhatIsPublished:
    def test_our_task_id_is_the_celery_id(self, runner):
        task_id = uuid.uuid4()
        settings = _settings()

        with patch.object(tasks.run_select_from_db, "apply_async") as apply_async:
            runner.run_select_from_db(
                task_id=task_id,
                assembly_id=(assembly_id := uuid.uuid4()),
                number_people_wanted=5,
                settings=settings,
                test_selection=True,
                targets_snapshot=[{"name": "Gender"}],
            )()

        apply_async.assert_called_once_with(
            kwargs={
                "task_id": task_id,
                "assembly_id": assembly_id,
                "number_people_wanted": 5,
                "settings": settings,
                "test_selection": True,
                "targets_snapshot": [{"name": "Gender"}],
            },
            task_id=str(task_id),
        )

    def test_time_limits_are_passed_only_when_given(self, runner):
        with patch.object(tasks.run_select, "apply_async") as apply_async:
            runner.run_select(
                task_id=uuid.uuid4(),
                data_source=None,  # type: ignore[arg-type]
                number_people_wanted=5,
                settings=_settings(),
                test_selection=False,
                gen_rem_tab=True,
            )()
            runner.run_select(
                task_id=uuid.uuid4(),
                data_source=None,  # type: ignore[arg-type]
                number_people_wanted=5,
                settings=_settings(),
                test_selection=False,
                gen_rem_tab=True,
                time_limit=300,
                soft_time_limit=270,
            )()

        without, with_limits = (call.kwargs for call in apply_async.call_args_list)
        assert "time_limit" not in without
        assert "soft_time_limit" not in without
        assert with_limits["time_limit"] == 300
        assert with_limits["soft_time_limit"] == 270

    def test_the_auto_export_is_sent_with_its_countdown_and_a_celery_id(self, runner):
        assembly_id = uuid.uuid4()

        with patch.object(tasks.auto_export_respondents, "apply_async") as apply_async:
            runner.auto_export_respondents(assembly_id=assembly_id, countdown=30)()

        apply_async.assert_called_once_with(kwargs={"assembly_id": assembly_id}, countdown=30)

    @pytest.mark.parametrize("dry_run", [True, False])
    def test_manage_old_tabs(self, runner, dry_run):
        task_id = uuid.uuid4()

        with patch.object(tasks.manage_old_tabs, "apply_async") as apply_async:
            runner.manage_old_tabs(task_id=task_id, data_source=None, dry_run=dry_run)()  # type: ignore[arg-type]

        apply_async.assert_called_once_with(
            kwargs={"task_id": task_id, "data_source": None, "dry_run": dry_run}, task_id=str(task_id)
        )

    def test_a_publish_error_is_raised_from_the_dispatch(self, runner):
        with patch.object(tasks.load_gsheet, "apply_async", side_effect=ConnectionError("broker down")):
            dispatch = runner.load_gsheet(task_id=uuid.uuid4(), data_source=None, settings=_settings())  # type: ignore[arg-type]
            with pytest.raises(ConnectionError, match="broker down"):
                dispatch()


class TestStatus:
    def test_a_successful_task_carries_its_return_value(self, runner):
        with patch.object(app, "AsyncResult", return_value=Mock(state="SUCCESS", result=(True, [], None))):
            assert runner.status("abc") == TaskStatus(state="SUCCESS", value=(True, [], None))

    @pytest.mark.parametrize("state", ["FAILURE", "REVOKED", "REJECTED"])
    def test_a_failed_task_carries_its_exception_message(self, runner, state):
        with patch.object(app, "AsyncResult", return_value=Mock(state=state, info=RuntimeError("boom"))):
            assert runner.status("abc") == TaskStatus(state=state, error="boom")

    def test_a_failure_stored_as_a_dict_gives_its_message(self, runner):
        result = Mock(state="FAILURE", info={"exc_message": "from the backend"})
        with patch.object(app, "AsyncResult", return_value=result):
            assert runner.status("abc").error == "from the backend"

    def test_a_failure_with_no_info_says_so(self, runner):
        with patch.object(app, "AsyncResult", return_value=Mock(state="FAILURE", info=None)):
            assert runner.status("abc").error == "No exception info available"

    @pytest.mark.parametrize("state", ["PENDING", "STARTED", "RETRY"])
    def test_an_unfinished_task_has_only_its_state(self, runner, state):
        with patch.object(app, "AsyncResult", return_value=Mock(state=state)):
            assert runner.status("abc") == TaskStatus(state=state)

    def test_it_never_calls_get_so_it_is_safe_inside_a_worker(self, runner):
        result = Mock(state="SUCCESS", result="value")
        result.get.side_effect = AssertionError("result.get() must not be called")
        with patch.object(app, "AsyncResult", return_value=result):
            assert runner.status("abc").value == "value"


def test_revoke_terminates_the_task(runner):
    with patch.object(app.control, "revoke") as revoke:
        runner.revoke("abc")

    revoke.assert_called_once_with("abc", terminate=True)
