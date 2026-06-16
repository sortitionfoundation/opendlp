"""ABOUTME: Contract tests for EmailTemplateRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid

from tests.contract.conftest import ContractBackend


class TestAddAndGet:
    def test_add_and_get_by_id(self, email_template_backend: ContractBackend):
        template = email_template_backend.make_email_template(name="Welcome")

        retrieved = email_template_backend.repo.get(template.id)
        assert retrieved is not None
        assert retrieved.id == template.id
        assert retrieved.name == "Welcome"
        assert retrieved.subject == "Thanks"
        assert retrieved.body_html == "<p>Hi</p>"

    def test_get_nonexistent_returns_none(self, email_template_backend: ContractBackend):
        assert email_template_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_templates(self, email_template_backend: ContractBackend):
        t1 = email_template_backend.make_email_template()
        t2 = email_template_backend.make_email_template()

        ids = {t.id for t in email_template_backend.repo.all()}
        assert t1.id in ids
        assert t2.id in ids


class TestListByAssembly:
    def test_lists_only_matching_assembly(self, email_template_backend: ContractBackend):
        assembly_id = email_template_backend.make_assembly().id
        mine = email_template_backend.make_email_template(assembly_id=assembly_id)
        other = email_template_backend.make_email_template()

        results = email_template_backend.repo.list_by_assembly(assembly_id)
        ids = {t.id for t in results}
        assert mine.id in ids
        assert other.id not in ids


class TestDelete:
    def test_delete_removes_template(self, email_template_backend: ContractBackend):
        template = email_template_backend.make_email_template()

        email_template_backend.repo.delete(template)
        email_template_backend.commit()

        assert email_template_backend.repo.get(template.id) is None
