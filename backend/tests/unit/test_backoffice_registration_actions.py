"""ABOUTME: Unit tests for _handle_registration_action dispatcher
ABOUTME: Verifies each action maps to the right service call and flash message"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from opendlp.domain.registration_page import RegistrationPageStatus
from opendlp.entrypoints.blueprints.backoffice import _handle_registration_action
from opendlp.entrypoints.flask_app import create_app


@pytest.fixture
def app_ctx():
    """Push a request context so flask-babel's `_()` (gettext) can resolve."""
    app = create_app("testing")
    with app.test_request_context():
        yield


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def assembly_id() -> uuid.UUID:
    return uuid.uuid4()


def _page_with_status(status: RegistrationPageStatus) -> MagicMock:
    page = MagicMock()
    page.status = status
    return page


class TestHandleRegistrationAction:
    """Each action string maps to a single service call and a flash message."""

    def test_publish_action_calls_publish_when_page_is_test(self, app_ctx, user_id, assembly_id):
        with (
            patch("opendlp.entrypoints.blueprints.backoffice.bootstrap.bootstrap"),
            patch("opendlp.entrypoints.blueprints.backoffice.get_registration_page_with_source") as get_page,
            patch("opendlp.entrypoints.blueprints.backoffice.publish_registration_page") as publish,
        ):
            get_page.return_value = (_page_with_status(RegistrationPageStatus.TEST), MagicMock())

            message = _handle_registration_action("publish", user_id, assembly_id)

            publish.assert_called_once()
            assert "published successfully" in message.lower()

    def test_publish_action_on_already_published_page_does_not_republish(self, app_ctx, user_id, assembly_id):
        with (
            patch("opendlp.entrypoints.blueprints.backoffice.bootstrap.bootstrap"),
            patch("opendlp.entrypoints.blueprints.backoffice.get_registration_page_with_source") as get_page,
            patch("opendlp.entrypoints.blueprints.backoffice.publish_registration_page") as publish,
        ):
            get_page.return_value = (_page_with_status(RegistrationPageStatus.PUBLISHED), MagicMock())

            message = _handle_registration_action("publish", user_id, assembly_id)

            publish.assert_not_called()
            assert "html updated" in message.lower()

    def test_unpublish_action_calls_unpublish(self, app_ctx, user_id, assembly_id):
        with (
            patch("opendlp.entrypoints.blueprints.backoffice.bootstrap.bootstrap"),
            patch("opendlp.entrypoints.blueprints.backoffice.unpublish_registration_page") as unpublish,
        ):
            message = _handle_registration_action("unpublish", user_id, assembly_id)

            unpublish.assert_called_once()
            assert "unpublished" in message.lower()

    def test_close_action_calls_close(self, app_ctx, user_id, assembly_id):
        with (
            patch("opendlp.entrypoints.blueprints.backoffice.bootstrap.bootstrap"),
            patch("opendlp.entrypoints.blueprints.backoffice.close_registration_page") as close,
        ):
            message = _handle_registration_action("close", user_id, assembly_id)

            close.assert_called_once()
            assert "closed" in message.lower()

    def test_reopen_action_calls_reopen(self, app_ctx, user_id, assembly_id):
        with (
            patch("opendlp.entrypoints.blueprints.backoffice.bootstrap.bootstrap"),
            patch("opendlp.entrypoints.blueprints.backoffice.reopen_registration_page") as reopen,
        ):
            message = _handle_registration_action("reopen", user_id, assembly_id)

            reopen.assert_called_once()
            assert "reopened" in message.lower()

    def test_save_action_uses_saved_message_for_test_pages(self, app_ctx, user_id, assembly_id):
        with (
            patch("opendlp.entrypoints.blueprints.backoffice.bootstrap.bootstrap"),
            patch("opendlp.entrypoints.blueprints.backoffice.get_registration_page_with_source") as get_page,
        ):
            get_page.return_value = (_page_with_status(RegistrationPageStatus.TEST), MagicMock())

            message = _handle_registration_action("save", user_id, assembly_id)

            assert "saved" in message.lower()
            assert "republished" not in message.lower()

    def test_save_action_uses_republished_message_when_page_published(self, app_ctx, user_id, assembly_id):
        with (
            patch("opendlp.entrypoints.blueprints.backoffice.bootstrap.bootstrap"),
            patch("opendlp.entrypoints.blueprints.backoffice.get_registration_page_with_source") as get_page,
        ):
            get_page.return_value = (_page_with_status(RegistrationPageStatus.PUBLISHED), MagicMock())

            message = _handle_registration_action("save", user_id, assembly_id)

            assert "republished" in message.lower()
