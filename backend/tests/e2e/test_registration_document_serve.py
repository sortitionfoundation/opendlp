"""ABOUTME: E2E smoke for serving registration documents from the database
ABOUTME: One PostgreSQL happy-path GET; richer behaviour lives in tests/component/"""

from datetime import UTC, datetime, timedelta

import pytest
from flask.testing import FlaskClient

from opendlp.domain.registration_document import RegistrationDocument
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.registration_document_service import add_registration_document
from opendlp.service_layer.registration_page_service import (
    create_registration_page_with_slugs,
    publish_registration_page,
    update_registration_page_html,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import route_url

MINIMAL_FORM_HTML = "<form method='post' action='{{ form_action }}'>{{ csrf_form_element }}</form>"


@pytest.fixture(autouse=True)
def enable_registration_feature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
    reload_flags()


def _pdf() -> bytes:
    return b"%PDF-1.7\n1 0 obj document body\n%%EOF\n"


def _seed_published_page_with_document(session_factory, admin_user) -> tuple[str, RegistrationDocument]:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Document Assembly",
            created_by_user_id=admin_user.id,
            question="Test question?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        assembly_id = assembly.id

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        page = create_registration_page_with_slugs(uow, admin_user.id, assembly_id)
        url_slug = page.url_slug

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        update_registration_page_html(uow, admin_user.id, assembly_id, MINIMAL_FORM_HTML)

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        publish_registration_page(uow, admin_user.id, assembly_id)

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        document = add_registration_document(uow, admin_user.id, assembly_id, _pdf(), original_filename="info pack.pdf")

    return url_slug, document


class TestServeRegistrationDocument:
    def test_serves_published_document_with_headers(
        self, client: FlaskClient, postgres_session_factory, admin_user
    ) -> None:
        url_slug, document = _seed_published_page_with_document(postgres_session_factory, admin_user)

        response = client.get(
            route_url(
                client,
                "registration.serve_registration_document",
                url_slug=url_slug,
                document_name=f"{document.sha256}.pdf",
            )
        )

        assert response.status_code == 200
        assert response.mimetype == "application/pdf"
        assert response.data == document.data
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Content-Disposition"].startswith("attachment")
        assert "info pack.pdf" in response.headers["Content-Disposition"]
        assert "immutable" in response.headers["Cache-Control"]
        assert response.get_etag()[0] == document.sha256
