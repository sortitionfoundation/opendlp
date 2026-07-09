"""ABOUTME: Unit tests for respondent service layer functions
ABOUTME: Uses FakeUnitOfWork to test service-level behaviour without a database"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole, RespondentAction, RespondentStatus
from opendlp.service_layer import respondent_service
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    InsufficientPermissions,
    InvalidSelection,
    RespondentNotFoundError,
    UserNotFoundError,
)
from tests.fakes import FakeUnitOfWork


def _seed(uow: FakeUnitOfWork, *, global_role: GlobalRole = GlobalRole.ADMIN) -> tuple[User, Assembly, Respondent]:
    user = User(email="admin@example.com", global_role=global_role, password_hash="hash")
    uow.users.add(user)

    assembly = Assembly(title="Test Assembly")
    uow.assemblies.add(assembly)

    respondent = Respondent(assembly_id=assembly.id, external_id="R001", email="alice@example.com")
    uow.respondents.add(respondent)

    return user, assembly, respondent


class TestGetRespondent:
    def test_returns_respondent_for_admin(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)

        result = respondent_service.get_respondent(uow, user.id, assembly.id, respondent.id)

        assert result.id == respondent.id
        assert result.external_id == "R001"
        assert result.email == "alice@example.com"

    def test_returns_detached_copy(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)

        result = respondent_service.get_respondent(uow, user.id, assembly.id, respondent.id)

        assert result is not respondent

    def test_raises_when_user_missing(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow)

        with pytest.raises(UserNotFoundError):
            respondent_service.get_respondent(uow, uuid.uuid4(), assembly.id, respondent.id)

    def test_raises_when_assembly_missing(self):
        uow = FakeUnitOfWork()
        user, _, respondent = _seed(uow)

        with pytest.raises(AssemblyNotFoundError):
            respondent_service.get_respondent(uow, user.id, uuid.uuid4(), respondent.id)

    def test_raises_when_user_lacks_permission(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow)
        outsider = User(email="outsider@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(outsider)

        with pytest.raises(InsufficientPermissions):
            respondent_service.get_respondent(uow, outsider.id, assembly.id, respondent.id)

    def test_raises_when_respondent_missing(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)

        with pytest.raises(RespondentNotFoundError):
            respondent_service.get_respondent(uow, user.id, assembly.id, uuid.uuid4())

    def test_raises_when_respondent_belongs_to_other_assembly(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)
        other_assembly = Assembly(title="Other")
        uow.assemblies.add(other_assembly)
        other_respondent = Respondent(assembly_id=other_assembly.id, external_id="R-OTHER")
        uow.respondents.add(other_respondent)

        with pytest.raises(RespondentNotFoundError):
            respondent_service.get_respondent(uow, user.id, assembly.id, other_respondent.id)


def _make_assembly_manager(uow: FakeUnitOfWork, assembly: Assembly) -> User:
    user = User(email=f"manager-{uuid.uuid4().hex[:6]}@example.com", global_role=GlobalRole.USER, password_hash="h")
    user.assembly_roles.append(
        UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER)
    )
    uow.users.add(user)
    return user


def _make_confirmation_caller(uow: FakeUnitOfWork, assembly: Assembly) -> User:
    user = User(email=f"caller-{uuid.uuid4().hex[:6]}@example.com", global_role=GlobalRole.USER, password_hash="h")
    user.assembly_roles.append(
        UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.CONFIRMATION_CALLER)
    )
    uow.users.add(user)
    return user


class TestDeleteRespondent:
    def test_admin_can_delete(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)

        respondent_service.delete_respondent(uow, user.id, assembly.id, respondent.id, comment="gdpr request")

        assert respondent.selection_status == RespondentStatus.DELETED
        assert respondent.email == ""
        assert len(respondent.comments) == 1
        assert respondent.comments[0].text == "gdpr request"
        assert respondent.comments[0].author_id == user.id
        assert respondent.comments[0].action is RespondentAction.DELETE

    def test_global_organiser_can_delete(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow, global_role=GlobalRole.GLOBAL_ORGANISER)

        respondent_service.delete_respondent(uow, user.id, assembly.id, respondent.id, comment="gdpr request")

        assert respondent.selection_status == RespondentStatus.DELETED

    def test_assembly_manager_can_delete(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow, global_role=GlobalRole.USER)
        manager = _make_assembly_manager(uow, assembly)

        respondent_service.delete_respondent(uow, manager.id, assembly.id, respondent.id, comment="gdpr request")

        assert respondent.selection_status == RespondentStatus.DELETED

    def test_confirmation_caller_cannot_delete(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow, global_role=GlobalRole.USER)
        caller = _make_confirmation_caller(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            respondent_service.delete_respondent(uow, caller.id, assembly.id, respondent.id, comment="gdpr request")
        assert respondent.selection_status == RespondentStatus.POOL

    def test_unrelated_user_cannot_delete(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow, global_role=GlobalRole.USER)
        outsider = User(email="outsider@example.com", global_role=GlobalRole.USER, password_hash="h")
        uow.users.add(outsider)

        with pytest.raises(InsufficientPermissions):
            respondent_service.delete_respondent(uow, outsider.id, assembly.id, respondent.id, comment="gdpr request")

    def test_empty_comment_rejected(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)

        with pytest.raises(ValueError, match="comment is required"):
            respondent_service.delete_respondent(uow, user.id, assembly.id, respondent.id, comment="")
        assert respondent.selection_status == RespondentStatus.POOL

    def test_whitespace_comment_rejected(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)

        with pytest.raises(ValueError, match="comment is required"):
            respondent_service.delete_respondent(uow, user.id, assembly.id, respondent.id, comment="   ")

    def test_raises_when_respondent_in_other_assembly(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)
        other = Assembly(title="Other")
        uow.assemblies.add(other)
        other_respondent = Respondent(assembly_id=other.id, external_id="R-X")
        uow.respondents.add(other_respondent)

        with pytest.raises(RespondentNotFoundError):
            respondent_service.delete_respondent(uow, user.id, assembly.id, other_respondent.id, comment="hi")

    def test_raises_when_respondent_missing(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)

        with pytest.raises(RespondentNotFoundError):
            respondent_service.delete_respondent(uow, user.id, assembly.id, uuid.uuid4(), comment="hi")

    def test_raises_when_user_missing(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow)

        with pytest.raises(UserNotFoundError):
            respondent_service.delete_respondent(uow, uuid.uuid4(), assembly.id, respondent.id, comment="hi")

    def test_raises_when_assembly_missing(self):
        uow = FakeUnitOfWork()
        user, _, respondent = _seed(uow)

        with pytest.raises(AssemblyNotFoundError):
            respondent_service.delete_respondent(uow, user.id, uuid.uuid4(), respondent.id, comment="hi")


class TestAddRespondentComment:
    def test_manager_can_add_comment(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow, global_role=GlobalRole.USER)
        manager = _make_assembly_manager(uow, assembly)

        respondent_service.add_respondent_comment(uow, manager.id, assembly.id, respondent.id, text="followed up")

        assert len(respondent.comments) == 1
        assert respondent.comments[0].text == "followed up"
        assert respondent.comments[0].action is RespondentAction.NONE
        assert respondent.comments[0].author_id == manager.id

    def test_confirmation_caller_cannot_add_comment(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow, global_role=GlobalRole.USER)
        caller = _make_confirmation_caller(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            respondent_service.add_respondent_comment(uow, caller.id, assembly.id, respondent.id, text="note")

    def test_empty_text_rejected(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)

        with pytest.raises(ValueError, match="Comment text is required"):
            respondent_service.add_respondent_comment(uow, user.id, assembly.id, respondent.id, text="")


class TestGetRespondentsIncludeDeleted:
    def test_excludes_deleted_by_default(self):
        uow = FakeUnitOfWork()
        user, assembly, live = _seed(uow)
        dead = Respondent(
            assembly_id=assembly.id,
            external_id="R-DEAD",
            selection_status=RespondentStatus.DELETED,
        )
        uow.respondents.add(dead)

        results = respondent_service.get_respondents_for_assembly(uow, user.id, assembly.id)
        assert {r.id for r in results} == {live.id}

    def test_includes_deleted_when_requested(self):
        uow = FakeUnitOfWork()
        user, assembly, live = _seed(uow)
        dead = Respondent(
            assembly_id=assembly.id,
            external_id="R-DEAD",
            selection_status=RespondentStatus.DELETED,
        )
        uow.respondents.add(dead)

        results = respondent_service.get_respondents_for_assembly(uow, user.id, assembly.id, include_deleted=True)
        assert {r.id for r in results} == {live.id, dead.id}


class TestGetRespondentWithCommentAuthors:
    def test_returns_detached_respondent_and_authors(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)
        other_author = User(email="author2@example.com", global_role=GlobalRole.USER, password_hash="h")
        uow.users.add(other_author)

        respondent.add_comment("note by admin", user.id)
        respondent.add_comment("note by other", other_author.id)

        fetched, authors = respondent_service.get_respondent_with_comment_authors(
            uow, user.id, assembly.id, respondent.id
        )

        assert fetched.id == respondent.id
        assert fetched is not respondent  # detached copy
        assert set(authors.keys()) == {user.id, other_author.id}
        assert authors[user.id].email == "admin@example.com"
        assert authors[other_author.id].email == "author2@example.com"

    def test_returns_empty_authors_when_no_comments(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)

        fetched, authors = respondent_service.get_respondent_with_comment_authors(
            uow, user.id, assembly.id, respondent.id
        )

        assert fetched.id == respondent.id
        assert authors == {}

    def test_skips_unknown_authors(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)
        missing_author_id = uuid.uuid4()
        # Manually append a comment authored by a user that no longer exists
        respondent.add_comment("ghost", missing_author_id)

        fetched, authors = respondent_service.get_respondent_with_comment_authors(
            uow, user.id, assembly.id, respondent.id
        )

        assert fetched.id == respondent.id
        assert missing_author_id not in authors

    def test_deduplicates_author_lookups(self):
        """Multiple comments by the same author should only produce one dict entry."""
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)

        respondent.add_comment("one", user.id)
        respondent.add_comment("two", user.id)
        respondent.add_comment("three", user.id)

        _, authors = respondent_service.get_respondent_with_comment_authors(uow, user.id, assembly.id, respondent.id)

        assert list(authors.keys()) == [user.id]

    def test_raises_when_user_missing(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow)

        with pytest.raises(UserNotFoundError):
            respondent_service.get_respondent_with_comment_authors(uow, uuid.uuid4(), assembly.id, respondent.id)

    def test_raises_when_assembly_missing(self):
        uow = FakeUnitOfWork()
        user, _, respondent = _seed(uow)

        with pytest.raises(AssemblyNotFoundError):
            respondent_service.get_respondent_with_comment_authors(uow, user.id, uuid.uuid4(), respondent.id)

    def test_raises_when_user_lacks_permission(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow)
        outsider = User(email="outsider@example.com", global_role=GlobalRole.USER, password_hash="h")
        uow.users.add(outsider)

        with pytest.raises(InsufficientPermissions):
            respondent_service.get_respondent_with_comment_authors(uow, outsider.id, assembly.id, respondent.id)

    def test_raises_when_respondent_in_other_assembly(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)
        other = Assembly(title="Other")
        uow.assemblies.add(other)
        other_respondent = Respondent(assembly_id=other.id, external_id="R-X")
        uow.respondents.add(other_respondent)

        with pytest.raises(RespondentNotFoundError):
            respondent_service.get_respondent_with_comment_authors(uow, user.id, assembly.id, other_respondent.id)


class TestGetRespondentsForAssemblyPaginated:
    def test_returns_paginated_respondents(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)
        # Add more respondents (seed already adds one)
        for i in range(4):
            uow.respondents.add(Respondent(assembly_id=assembly.id, external_id=f"R{i:03d}"))

        results, total_count = respondent_service.get_respondents_for_assembly_paginated(
            uow, user.id, assembly.id, page=1, per_page=2
        )

        assert len(results) == 2
        assert total_count == 5  # 1 from seed + 4 added

    def test_returns_detached_copies(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)

        results, _ = respondent_service.get_respondents_for_assembly_paginated(
            uow, user.id, assembly.id, page=1, per_page=10
        )

        assert results[0] is not respondent

    def test_filters_by_status(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)  # seed adds one POOL respondent
        # Add a SELECTED respondent
        selected = Respondent(
            assembly_id=assembly.id, external_id="R-SELECTED", selection_status=RespondentStatus.SELECTED
        )
        uow.respondents.add(selected)

        results, total_count = respondent_service.get_respondents_for_assembly_paginated(
            uow, user.id, assembly.id, page=1, per_page=10, status=RespondentStatus.SELECTED
        )

        assert len(results) == 1
        assert total_count == 1
        assert results[0].selection_status == RespondentStatus.SELECTED


class TestCreateRespondentEmitsCreateComment:
    def test_manual_create_records_create_comment(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)

        resp = respondent_service.create_respondent(
            uow,
            user.id,
            assembly.id,
            external_id="MANUAL-1",
            attributes={"Gender": "Female"},
        )

        create_comments = [c for c in resp.comments if c.action is RespondentAction.CREATE]
        assert len(create_comments) == 1
        assert "manual entry" in create_comments[0].text
        assert create_comments[0].author_id == user.id

    def test_csv_import_records_create_comment_per_row_with_filename(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)
        csv_content = "external_id,Gender\nCSV-1,Female\nCSV-2,Male\n"

        respondents, _errors, _id_col = respondent_service.import_respondents_from_csv(
            uow,
            user.id,
            assembly.id,
            csv_content,
            filename="people.csv",
        )

        assert len(respondents) == 2
        for r in respondents:
            create_comments = [c for c in r.comments if c.action is RespondentAction.CREATE]
            assert len(create_comments) == 1
            assert "CSV import" in create_comments[0].text
            assert "people.csv" in create_comments[0].text
            assert create_comments[0].author_id == user.id


class TestImportRespondentsFromRows:
    # Row-to-Respondent mapping (attributes, flags, internal columns, comment) is
    # covered directly in TestRespondentFromRow. These tests cover the
    # orchestration: id-column resolution, deduplication, and permissions.
    def test_auto_detects_id_column_from_first_column(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)
        headers = ["person_id", "Gender"]
        rows = [{"person_id": "ROW-1", "Gender": "Female"}, {"person_id": "ROW-2", "Gender": "Male"}]

        respondents, errors, id_col = respondent_service.import_respondents_from_rows(
            uow, user.id, assembly.id, headers, rows
        )

        assert errors == []
        assert id_col == "person_id"
        assert {r.external_id for r in respondents} == {"ROW-1", "ROW-2"}

    def test_skips_empty_and_duplicate_ids(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)
        headers = ["external_id", "Gender"]
        rows = [
            {"external_id": "R1", "Gender": "Female"},
            {"external_id": "  ", "Gender": "Male"},  # empty id → skipped
            {"external_id": "R1", "Gender": "Other"},  # duplicate within import → skipped
        ]

        respondents, errors, _id = respondent_service.import_respondents_from_rows(
            uow, user.id, assembly.id, headers, rows
        )

        assert [r.external_id for r in respondents] == ["R1"]
        assert len(errors) == 2
        # Errors carry the file line number (header is line 1, so data starts at 2).
        assert any(e.startswith("Row 3:") and "empty" in e for e in errors)
        assert any(e.startswith("Row 4:") and "duplicate" in e.lower() for e in errors)

    def test_empty_headers_raise(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)
        with pytest.raises(InvalidSelection):
            respondent_service.import_respondents_from_rows(uow, user.id, assembly.id, [], [])

    def test_requires_manage_permission(self):
        uow = FakeUnitOfWork()
        user = User(email="plain@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(user)
        assembly = Assembly(title="Locked")
        uow.assemblies.add(assembly)
        with pytest.raises(InsufficientPermissions):
            respondent_service.import_respondents_from_rows(
                uow, user.id, assembly.id, ["external_id"], [{"external_id": "R1"}]
            )


class TestImportSkipsInternalColumns:
    # That the internal columns are discarded from attributes is covered by
    # TestRespondentFromRow.test_discards_internal_columns. This test covers the
    # import-level behaviour: the columns are reported to the organiser, and a
    # re-imported (previously exported) row lands back in POOL.
    def test_internal_columns_are_reported_and_reset_to_pool(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)
        headers = ["external_id", "Gender", "selection_status", "source_type", "selection_run_id"]
        rows = [
            {
                "external_id": "R1",
                "Gender": "Female",
                "selection_status": "SELECTED",
                "source_type": "CSV_IMPORT",
                "selection_run_id": "abc",
            }
        ]

        respondents, errors, _id = respondent_service.import_respondents_from_rows(
            uow, user.id, assembly.id, headers, rows
        )

        # A new record imported afresh keeps the default POOL status, even though
        # the row said SELECTED.
        assert respondents[0].selection_status == RespondentStatus.POOL
        # The skipped columns are reported so the organiser knows they were ignored.
        assert any("selection_status" in e for e in errors)


class TestRespondentFromRow:
    def test_maps_id_column_and_attributes(self):
        row = {"external_id": "R1", "Gender": "Female", "Age": "42"}
        respondent = respondent_service.respondent_from_row(uuid.uuid4(), uuid.uuid4(), row, "R1", "external_id")
        assert respondent.external_id == "R1"
        assert respondent.attributes == {"Gender": "Female", "Age": "42"}

    def test_extracts_boolean_flags_and_email(self):
        row = {
            "external_id": "R1",
            "email": "a@b.com",
            "consent": "true",
            "eligible": "true",
            "can_attend": "false",
            "stay_on_db": "true",
        }
        respondent = respondent_service.respondent_from_row(uuid.uuid4(), uuid.uuid4(), row, "R1", "external_id")
        assert respondent.email == "a@b.com"
        assert respondent.consent is True
        assert respondent.eligible is True
        assert respondent.can_attend is False
        assert respondent.stay_on_db is True
        # The lifted fields must not linger in attributes.
        for key in ("email", "consent", "eligible", "can_attend", "stay_on_db"):
            assert key not in respondent.attributes

    def test_missing_flags_are_none(self):
        respondent = respondent_service.respondent_from_row(
            uuid.uuid4(), uuid.uuid4(), {"external_id": "R1"}, "R1", "external_id"
        )
        assert respondent.consent is None
        assert respondent.eligible is None
        assert respondent.can_attend is None
        assert respondent.stay_on_db is None

    def test_discards_internal_columns(self):
        row = {"external_id": "R1", "Gender": "Female", "selection_status": "SELECTED", "source_type": "CSV_IMPORT"}
        respondent = respondent_service.respondent_from_row(uuid.uuid4(), uuid.uuid4(), row, "R1", "external_id")
        assert respondent.attributes == {"Gender": "Female"}

    def test_adds_create_comment_with_filename(self):
        user_id = uuid.uuid4()
        respondent = respondent_service.respondent_from_row(
            uuid.uuid4(), user_id, {"external_id": "R1"}, "R1", "external_id", filename="people.csv"
        )
        create_comments = [c for c in respondent.comments if c.action == RespondentAction.CREATE]
        assert len(create_comments) == 1
        assert "people.csv" in create_comments[0].text
        assert create_comments[0].author_id == user_id
