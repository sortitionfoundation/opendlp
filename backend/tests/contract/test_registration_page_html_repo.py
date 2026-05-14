"""ABOUTME: Contract tests for RegistrationPageHtmlRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from typing import Any

from opendlp.domain.registration_page import RegistrationPageHtml
from tests.contract.conftest import ContractBackend


def _add_html(
    backend: ContractBackend, registration_page_id: uuid.UUID | None = None, **kwargs: Any
) -> RegistrationPageHtml:
    if registration_page_id is None:
        registration_page_id = backend.make_registration_page().id
    html = RegistrationPageHtml(registration_page_id=registration_page_id, **kwargs)
    backend.repo.add(html)
    backend.commit()
    return html


class TestAddAndGet:
    def test_add_and_get_by_id(self, registration_page_html_backend: ContractBackend):
        html = _add_html(registration_page_html_backend, form_html="<form></form>")

        retrieved = registration_page_html_backend.repo.get(html.id)
        assert retrieved is not None
        assert retrieved.id == html.id
        assert retrieved.form_html == "<form></form>"

    def test_get_nonexistent_returns_none(self, registration_page_html_backend: ContractBackend):
        assert registration_page_html_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_sources(self, registration_page_html_backend: ContractBackend):
        h1 = _add_html(registration_page_html_backend)
        h2 = _add_html(registration_page_html_backend)

        ids = {h.id for h in registration_page_html_backend.repo.all()}
        assert h1.id in ids
        assert h2.id in ids


class TestGetByPageId:
    def test_finds_by_page_id(self, registration_page_html_backend: ContractBackend):
        page = registration_page_html_backend.make_registration_page()
        html = _add_html(registration_page_html_backend, registration_page_id=page.id)

        retrieved = registration_page_html_backend.repo.get_by_page_id(page.id)
        assert retrieved is not None
        assert retrieved.id == html.id

    def test_returns_none_when_page_has_no_source(self, registration_page_html_backend: ContractBackend):
        assert registration_page_html_backend.repo.get_by_page_id(uuid.uuid4()) is None


class TestDelete:
    def test_delete_removes_source(self, registration_page_html_backend: ContractBackend):
        html = _add_html(registration_page_html_backend)

        registration_page_html_backend.repo.delete(html)
        registration_page_html_backend.commit()

        assert registration_page_html_backend.repo.get(html.id) is None
