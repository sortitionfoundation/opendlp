"""ABOUTME: Tests for the collection-time guard against hand-rolled fakes of boundaries that have a fake
ABOUTME: Each sample is split with + so that this file's own source does not trip the guard"""

import pytest

from tests.conftest import _HAND_ROLLED_FAKES


def _messages_for(source: str) -> list[str]:
    return [message for pattern, message in _HAND_ROLLED_FAKES if pattern.search(source)]


@pytest.mark.parametrize(
    "source",
    [
        'monkeypatch.setattr("opendlp.entrypoints.blueprints.admin.get_email' + '_adapter", lambda: adapter)',
        'monkeypatch.setattr(be_reg.bootstrap, "get_email' + '_adapter", lambda: adapter)',
        'with patch("opendlp.entrypoints.blueprints.registration.bootstrap.get_email' + '_adapter", return_value=a):',
    ],
)
def test_patching_get_email_adapter_points_to_email_outbox(source: str) -> None:
    assert _messages_for(source) == ["patches get_email_adapter - use the email_outbox fixture (tests/conftest.py)"]


@pytest.mark.parametrize(
    "source",
    [
        "adapter.send" + "_email.return_value = True",
        "adapter.send" + '_email.side_effect = RuntimeError("smtp down")',
        "email_adapter.send" + "_email.assert_called_once()",
        "email_adapter.send" + "_email.assert_not_called()",
        "kwargs = adapter.send" + '_email.call_args.kwargs["to"]',
        "assert adapter.send" + "_email.called",
        "adapter = MagicMock(spec=Email" + "Adapter)",
    ],
)
def test_mocking_an_email_adapter_points_to_the_fake(source: str) -> None:
    assert _messages_for(source) == [
        "mocks an email adapter - use FakeEmailAdapter, or the email_outbox fixture in a Flask test"
    ]


@pytest.mark.parametrize(
    "source",
    [
        'with patch("opendlp.service_layer.sortition.tasks.run_select.de' + 'lay") as mock_delay:',
        'with patch("opendlp.entrypoints.celery.tasks.load_gsheet.apply' + '_async"):',
        'with patch.object(tasks.manage_old_tabs, "apply' + '_async") as apply:',
        '@patch("opendlp.service_layer.sortition.tasks.run_select_from_db.de' + 'lay")',
    ],
)
def test_patching_a_celery_dispatch_points_to_the_task_runner(source: str) -> None:
    assert _messages_for(source) == [
        "patches a Celery dispatch - assert on task_runner.submitted (the task_runner fixture)"
    ]


@pytest.mark.parametrize(
    "source",
    [
        'with patch("opendlp.service_layer.sortition.app.app.Async' + 'Result") as result:',
        'with patch.object(app, "Async' + 'Result", return_value=result):',
        'with patch("opendlp.service_layer.sortition.app.app.control.re' + 'voke") as revoke:',
        'with patch.object(app.control, "re' + 'voke"):',
    ],
)
def test_patching_a_celery_result_or_revoke_points_to_the_task_runner(source: str) -> None:
    assert _messages_for(source) == [
        "patches a Celery result or revoke - use task_runner.finish/fail/set_state and task_runner.revoked"
    ]


@pytest.mark.parametrize(
    "source",
    [
        "adapter = FakeEmailAdapter(succeed=False)",
        'assert email_outbox.sent[0]["to"] == ["ada@example.com"]',
        "from opendlp.bootstrap import get_email" + "_adapter",
        "adapter = get_email" + "_adapter()",
        'with patch("smtplib.SMTP") as smtp:',
        'assert task_runner.submitted[0].kwargs["number_people_wanted"] == 6',
        "task_runner.finish(task_id, value=(True, [], report))",
        'with patch.object(load_gsheet, "update_state"):',
    ],
)
def test_using_the_fake_or_the_real_adapter_passes(source: str) -> None:
    assert _messages_for(source) == []
