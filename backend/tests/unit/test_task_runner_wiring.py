"""ABOUTME: Tests for how the task runner reaches the code: bootstrap's process runner and the event handlers
ABOUTME: Also covers the RecordingTaskRunner fake that the rest of the suite relies on"""

import pickle
import uuid

import pytest

from opendlp import bootstrap
from opendlp.domain import events
from opendlp.entrypoints.celery.runner import CeleryTaskRunner
from opendlp.service_layer import handlers, respondent_auto_export
from opendlp.service_layer.task_runner import TaskStatus
from tests.fakes import RecordingTaskRunner, SubmittedTask


class TestProcessTaskRunner:
    def test_the_test_suite_installs_a_recording_runner(self, task_runner):
        assert bootstrap.get_task_runner() is task_runner

    def test_with_none_set_it_is_the_celery_runner(self):
        bootstrap.set_task_runner(None)

        runner = bootstrap.get_task_runner()

        assert isinstance(runner, CeleryTaskRunner)
        assert bootstrap.get_task_runner() is runner

    def test_set_task_runner_replaces_it(self):
        other = RecordingTaskRunner()

        bootstrap.set_task_runner(other)

        assert bootstrap.get_task_runner() is other


class TestEventHandlersGetTheRunner:
    @pytest.mark.parametrize("event_class", [events.RespondentsChanged, events.RespondentSchemaChanged])
    def test_each_handler_is_given_the_runner(self, event_class):
        runner = RecordingTaskRunner()

        (handler,) = handlers.build_event_handlers(runner)[event_class]

        assert handler.func is respondent_auto_export.handle_respondents_changed
        assert handler.keywords == {"task_runner": runner}

    def test_the_default_handlers_use_the_process_runner(self, task_runner):
        (handler,) = bootstrap.default_event_handlers()[events.RespondentsChanged]

        assert handler.keywords == {"task_runner": task_runner}


class TestRecordingTaskRunner:
    def test_a_task_is_recorded_only_when_dispatched(self):
        runner = RecordingTaskRunner()
        assembly_id = uuid.uuid4()

        dispatch = runner.auto_export_respondents(assembly_id=assembly_id, countdown=30)
        assert runner.submitted == []
        dispatch()

        assert runner.submitted == [
            SubmittedTask(
                name="auto_export_respondents", kwargs={"assembly_id": assembly_id}, options={"countdown": 30}
            )
        ]

    def test_an_argument_that_cannot_be_pickled_fails_when_prepared(self):
        runner = RecordingTaskRunner()

        with pytest.raises((AttributeError, TypeError, pickle.PicklingError)):
            runner.manage_old_tabs(task_id=uuid.uuid4(), data_source=lambda: None, dry_run=True)  # type: ignore[arg-type]

    def test_fail_dispatch_raises_once_and_records_nothing(self):
        runner = RecordingTaskRunner()
        runner.fail_dispatch = ConnectionError("broker down")

        with pytest.raises(ConnectionError):
            runner.auto_export_respondents(assembly_id=uuid.uuid4(), countdown=30)()
        runner.auto_export_respondents(assembly_id=uuid.uuid4(), countdown=30)()

        assert len(runner.submitted) == 1

    def test_on_dispatch_sees_each_task_as_it_is_sent(self):
        runner = RecordingTaskRunner()
        seen = []
        runner.on_dispatch = seen.append

        runner.auto_export_respondents(assembly_id=uuid.uuid4(), countdown=30)()

        assert seen == runner.submitted

    def test_status_is_pending_until_set(self):
        runner = RecordingTaskRunner()
        task_id = uuid.uuid4()

        assert runner.status(str(task_id)) == TaskStatus(state="PENDING")
        runner.set_state(task_id, "STARTED")
        assert runner.status(str(task_id)) == TaskStatus(state="STARTED")
        runner.finish(task_id, value=(True, [], None))
        assert runner.status(str(task_id)) == TaskStatus(state="SUCCESS", value=(True, [], None))
        runner.fail(task_id, error="boom", state="REVOKED")
        assert runner.status(str(task_id)) == TaskStatus(state="REVOKED", error="boom")

    def test_revoke_is_recorded(self):
        runner = RecordingTaskRunner()

        runner.revoke("abc")

        assert runner.revoked == ["abc"]
