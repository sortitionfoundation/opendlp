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
        "adapter = FakeEmailAdapter(succeed=False)",
        'assert email_outbox.sent[0]["to"] == ["ada@example.com"]',
        "from opendlp.bootstrap import get_email" + "_adapter",
        "adapter = get_email" + "_adapter()",
        'with patch("smtplib.SMTP") as smtp:',
    ],
)
def test_using_the_fake_or_the_real_adapter_passes(source: str) -> None:
    assert _messages_for(source) == []
