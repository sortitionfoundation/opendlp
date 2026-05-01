"""ABOUTME: Integration tests for respondent service functions
ABOUTME: Tests respondent creation, CSV import, and retrieval service functions"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, GlobalRole, RespondentStatus
from opendlp.service_layer import respondent_service
from opendlp.service_layer.exceptions import InsufficientPermissions, RespondentNotFoundError
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import grant_user_assembly_role


@pytest.fixture
def uow(postgres_session_factory):
    """Create a UnitOfWork for testing."""
    return SqlAlchemyUnitOfWork(postgres_session_factory)


@pytest.fixture
def admin_user(uow):
    """Create an admin user."""
    user = User(email="admin@test.com", global_role=GlobalRole.ADMIN, password_hash="hash123")
    with uow:
        uow.users.add(user)
        detached_user = user.create_detached_copy()
        uow.commit()
        return detached_user


@pytest.fixture
def test_assembly(uow):
    """Create a test assembly."""
    assembly = Assembly(title="Test Assembly", question="Test?", number_to_select=30)
    with uow:
        uow.assemblies.add(assembly)
        detached_assembly = assembly.create_detached_copy()
        uow.commit()
        return detached_assembly


class TestCreateRespondent:
    def test_create_respondent_success(self, uow, admin_user: User, test_assembly: Assembly):
        """Test creating a respondent."""
        resp = respondent_service.create_respondent(
            uow,
            admin_user.id,
            test_assembly.id,
            external_id="NB001",
            attributes={"Gender": "Female", "Age": "30-44"},
            email="alice@test.com",
            eligible=True,
        )

        assert resp.external_id == "NB001"
        assert resp.attributes["Gender"] == "Female"
        assert resp.email == "alice@test.com"
        assert resp.eligible is True

        # Verify it was persisted
        with uow:
            retrieved = uow.respondents.get(resp.id)
            assert retrieved is not None
            assert retrieved.external_id == "NB001"

    def test_create_duplicate_raises_error(self, uow, admin_user: User, test_assembly: Assembly):
        """Test creating duplicate respondent raises error."""
        respondent_service.create_respondent(uow, admin_user.id, test_assembly.id, external_id="NB001", attributes={})

        with pytest.raises(ValueError, match="already exists"):
            respondent_service.create_respondent(
                uow, admin_user.id, test_assembly.id, external_id="NB001", attributes={}
            )

    def test_create_with_nullable_boolean_fields(self, uow, admin_user: User, test_assembly: Assembly):
        """Test creating respondent with nullable boolean fields."""
        resp = respondent_service.create_respondent(
            uow,
            admin_user.id,
            test_assembly.id,
            external_id="NB001",
            attributes={},
            consent=None,
            eligible=None,
        )

        assert resp.consent is None
        assert resp.eligible is None

    def test_create_without_permission(self, uow, test_assembly: Assembly):
        """Test creating respondent without permission raises error."""
        user = User(email="user@test.com", global_role=GlobalRole.USER, password_hash="hash123")
        with uow:
            uow.users.add(user)
            user_id = user.id
            uow.commit()

        with pytest.raises(InsufficientPermissions):
            respondent_service.create_respondent(uow, user_id, test_assembly.id, external_id="NB001", attributes={})


class TestImportRespondentsFromCSV:
    def test_import_valid_csv(self, uow, admin_user: User, test_assembly: Assembly):
        """Test importing valid CSV data."""
        csv_content = """external_id,Gender,Age,email
NB001,Female,30-44,alice@test.com
NB002,Male,16-29,bob@test.com"""

        respondents, errors, resolved_id_column = respondent_service.import_respondents_from_csv(
            uow, admin_user.id, test_assembly.id, csv_content
        )

        assert len(respondents) == 2
        assert respondents[0].external_id == "NB001"
        assert respondents[0].attributes["Gender"] == "Female"
        assert respondents[0].email == "alice@test.com"
        assert len(errors) == 0
        assert resolved_id_column == "external_id"

        # Verify they were persisted
        with uow:
            all_resp = uow.respondents.get_by_assembly_id(test_assembly.id)
            assert len(all_resp) == 2

    def test_import_csv_uses_first_column_as_id(self, uow, admin_user: User, test_assembly: Assembly):
        """Test importing CSV without explicit id_column uses first column."""
        csv_content = """name,age
Alice,30"""

        respondents, _, resolved_id_column = respondent_service.import_respondents_from_csv(
            uow, admin_user.id, test_assembly.id, csv_content
        )

        assert resolved_id_column == "name"
        assert len(respondents) == 1
        assert respondents[0].external_id == "Alice"

    def test_import_skips_duplicates(self, uow, admin_user: User, test_assembly: Assembly):
        """Test importing CSV with duplicates skips them."""
        csv_content = """external_id,Gender
NB001,Female
NB001,Male"""

        respondents, errors, _ = respondent_service.import_respondents_from_csv(
            uow, admin_user.id, test_assembly.id, csv_content
        )

        assert len(respondents) == 1
        assert len(errors) == 1
        assert "duplicate" in errors[0].lower()

    def test_import_skips_empty_external_id(self, uow, admin_user: User, test_assembly: Assembly):
        """Test importing CSV with empty external_id skips row."""
        csv_content = """external_id,Gender
,Female
NB001,Male"""

        respondents, errors, _ = respondent_service.import_respondents_from_csv(
            uow, admin_user.id, test_assembly.id, csv_content
        )

        assert len(respondents) == 1
        assert respondents[0].external_id == "NB001"
        assert len(errors) == 1
        assert "empty external_id" in errors[0]

    def test_import_with_replace_existing(self, uow, admin_user: User, test_assembly: Assembly):
        """Test replacing existing respondents with new import."""
        # First import
        csv1 = """external_id,Gender
NB001,Female"""

        respondent_service.import_respondents_from_csv(uow, admin_user.id, test_assembly.id, csv1)

        # Verify first import
        with uow:
            all_resp = uow.respondents.get_by_assembly_id(test_assembly.id)
            assert len(all_resp) == 1

        # Second import with replace
        csv2 = """external_id,Age
NB002,30-44"""

        respondents, _, _ = respondent_service.import_respondents_from_csv(
            uow, admin_user.id, test_assembly.id, csv2, replace_existing=True
        )

        assert len(respondents) == 1
        assert respondents[0].external_id == "NB002"

        # Verify old respondent is gone
        with uow:
            all_resp = uow.respondents.get_by_assembly_id(test_assembly.id)
            assert len(all_resp) == 1
            assert all_resp[0].external_id == "NB002"

    def test_import_with_nullable_boolean_fields(self, uow, admin_user: User, test_assembly: Assembly):
        """Test importing CSV without boolean fields leaves them as None."""
        csv_content = """external_id,Gender
NB001,Female"""

        respondents, _, _ = respondent_service.import_respondents_from_csv(
            uow, admin_user.id, test_assembly.id, csv_content
        )

        assert len(respondents) == 1
        # Boolean fields should be None when not in CSV
        assert respondents[0].consent is None
        assert respondents[0].eligible is None
        assert respondents[0].can_attend is None

    def test_import_with_boolean_fields(self, uow, admin_user: User, test_assembly: Assembly):
        """Test importing CSV with boolean fields."""
        csv_content = """external_id,Gender,consent,eligible,can_attend
NB001,Female,true,true,false
NB002,Male,false,true,true"""

        respondents, _, _ = respondent_service.import_respondents_from_csv(
            uow, admin_user.id, test_assembly.id, csv_content
        )

        assert len(respondents) == 2
        assert respondents[0].consent is True
        assert respondents[0].eligible is True
        assert respondents[0].can_attend is False
        assert respondents[1].consent is False

    def test_import_without_permission(self, uow, test_assembly: Assembly):
        """Test importing without permission raises error."""
        user = User(email="user@test.com", global_role=GlobalRole.USER, password_hash="hash123")
        with uow:
            uow.users.add(user)
            user_id = user.id
            uow.commit()

        csv_content = """external_id,Gender
NB001,Female"""

        with pytest.raises(InsufficientPermissions):
            respondent_service.import_respondents_from_csv(uow, user_id, test_assembly.id, csv_content)


class TestResetSelectionStatus:
    def test_reset_all_to_pool(self, uow, admin_user: User, test_assembly: Assembly):
        """Test resetting all respondents back to POOL status."""
        # Create respondents with different statuses
        respondent_service.create_respondent(
            uow,
            admin_user.id,
            test_assembly.id,
            external_id="NB001",
            attributes={},
            selection_status=RespondentStatus.SELECTED,
        )
        respondent_service.create_respondent(
            uow,
            admin_user.id,
            test_assembly.id,
            external_id="NB002",
            attributes={},
            selection_status=RespondentStatus.CONFIRMED,
        )
        respondent_service.create_respondent(
            uow,
            admin_user.id,
            test_assembly.id,
            external_id="NB003",
            attributes={},
            selection_status=RespondentStatus.POOL,
        )

        count = respondent_service.reset_selection_status(uow, admin_user.id, test_assembly.id)

        assert count == 3

        # Verify all are now POOL
        with uow:
            all_resp = uow.respondents.get_by_assembly_id(test_assembly.id)
            for r in all_resp:
                assert r.selection_status == RespondentStatus.POOL
                assert r.selection_run_id is None

    def test_reset_without_permission(self, uow, test_assembly: Assembly):
        """Test resetting without permission raises error."""
        user = User(email="user@test.com", global_role=GlobalRole.USER, password_hash="hash123")
        with uow:
            uow.users.add(user)
            user_id = user.id
            uow.commit()

        with pytest.raises(InsufficientPermissions):
            respondent_service.reset_selection_status(uow, user_id, test_assembly.id)

    def test_reset_empty_assembly(self, uow, admin_user: User, test_assembly: Assembly):
        """Test resetting with no respondents returns zero."""
        count = respondent_service.reset_selection_status(uow, admin_user.id, test_assembly.id)
        assert count == 0


class TestCountNonPoolRespondents:
    def test_count_non_pool_with_mixed_statuses(self, uow, admin_user: User, test_assembly: Assembly):
        """Test counting non-POOL respondents with mixed statuses."""
        respondent_service.create_respondent(
            uow,
            admin_user.id,
            test_assembly.id,
            external_id="NB001",
            attributes={},
            selection_status=RespondentStatus.SELECTED,
        )
        respondent_service.create_respondent(
            uow,
            admin_user.id,
            test_assembly.id,
            external_id="NB002",
            attributes={},
            selection_status=RespondentStatus.CONFIRMED,
        )
        respondent_service.create_respondent(
            uow,
            admin_user.id,
            test_assembly.id,
            external_id="NB003",
            attributes={},
            selection_status=RespondentStatus.POOL,
        )

        with uow:
            count = respondent_service.count_non_pool_respondents(uow, test_assembly.id)

        assert count == 2

    def test_count_non_pool_all_pool(self, uow, admin_user: User, test_assembly: Assembly):
        """Test counting non-POOL respondents when all are POOL."""
        respondent_service.create_respondent(
            uow,
            admin_user.id,
            test_assembly.id,
            external_id="NB001",
            attributes={},
        )
        respondent_service.create_respondent(
            uow,
            admin_user.id,
            test_assembly.id,
            external_id="NB002",
            attributes={},
        )

        with uow:
            count = respondent_service.count_non_pool_respondents(uow, test_assembly.id)

        assert count == 0

    def test_count_non_pool_empty_assembly(self, uow, admin_user: User, test_assembly: Assembly):
        """Test counting non-POOL respondents for assembly with no respondents."""
        with uow:
            count = respondent_service.count_non_pool_respondents(uow, test_assembly.id)

        assert count == 0


class TestGetRespondentsForAssembly:
    def test_get_empty_respondents(self, uow, admin_user: User, test_assembly: Assembly):
        """Test getting respondents for assembly with no respondents."""
        respondents = respondent_service.get_respondents_for_assembly(uow, admin_user.id, test_assembly.id)
        assert respondents == []

    def test_get_all_respondents(self, uow, admin_user: User, test_assembly: Assembly):
        """Test getting all respondents for assembly."""
        csv_content = """external_id,Gender
NB001,Female
NB002,Male"""

        respondent_service.import_respondents_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

        respondents = respondent_service.get_respondents_for_assembly(uow, admin_user.id, test_assembly.id)
        assert len(respondents) == 2

    def test_get_respondents_filtered_by_status(self, uow, admin_user: User, test_assembly: Assembly):
        """Test filtering respondents by status."""
        # Create respondents with different statuses
        respondent_service.create_respondent(
            uow,
            admin_user.id,
            test_assembly.id,
            external_id="NB003",
            attributes={},
            selection_status=RespondentStatus.POOL,
        )
        respondent_service.create_respondent(
            uow,
            admin_user.id,
            test_assembly.id,
            external_id="NB004",
            attributes={},
            selection_status=RespondentStatus.SELECTED,
        )

        # Filter by POOL
        pool_resp = respondent_service.get_respondents_for_assembly(
            uow, admin_user.id, test_assembly.id, status=RespondentStatus.POOL
        )
        assert len(pool_resp) == 1
        assert pool_resp[0].external_id == "NB003"

        # Filter by SELECTED
        selected_resp = respondent_service.get_respondents_for_assembly(
            uow, admin_user.id, test_assembly.id, status=RespondentStatus.SELECTED
        )
        assert len(selected_resp) == 1
        assert selected_resp[0].external_id == "NB004"

    def test_get_respondents_without_permission(self, uow, test_assembly: Assembly):
        """Test getting respondents without permission raises error."""
        user = User(email="user@test.com", global_role=GlobalRole.USER, password_hash="hash123")
        with uow:
            uow.users.add(user)
            user_id = user.id
            uow.commit()

        with pytest.raises(InsufficientPermissions):
            respondent_service.get_respondents_for_assembly(uow, user_id, test_assembly.id)


class TestTransitionRespondentStatus:
    def _create(self, uow, admin_user, assembly, status=RespondentStatus.POOL):
        return respondent_service.create_respondent(
            uow,
            admin_user.id,
            assembly.id,
            external_id=f"R-ST-{uuid.uuid4().hex[:4]}",
            attributes={},
            selection_status=status,
        )

    def test_pool_to_selected_requires_manage(self, uow, admin_user, test_assembly):
        resp = self._create(uow, admin_user, test_assembly, RespondentStatus.POOL)
        respondent_service.transition_respondent_status(
            uow,
            admin_user.id,
            test_assembly.id,
            resp.id,
            new_status=RespondentStatus.SELECTED,
            comment="manual override",
        )
        with uow:
            retrieved = uow.respondents.get(resp.id)
            assert retrieved is not None
            assert retrieved.selection_status == RespondentStatus.SELECTED

    def _make_caller(self, uow, admin_user, assembly, email: str) -> uuid.UUID:
        caller = User(email=email, global_role=GlobalRole.USER, password_hash="h")
        with uow:
            uow.users.add(caller)
            caller_id = caller.id
            uow.commit()
        with uow:
            granter = uow.users.get(admin_user.id)
            grant_user_assembly_role(
                uow,
                user_id=caller_id,
                assembly_id=assembly.id,
                role=AssemblyRole.CONFIRMATION_CALLER,
                current_user=granter,
            )
        return caller_id

    def test_selected_to_confirmed_allowed_for_confirmation_caller(self, uow, admin_user, test_assembly):
        caller_id = self._make_caller(uow, admin_user, test_assembly, "caller@test.com")
        resp = self._create(uow, admin_user, test_assembly, RespondentStatus.SELECTED)

        respondent_service.transition_respondent_status(
            uow,
            caller_id,
            test_assembly.id,
            resp.id,
            new_status=RespondentStatus.CONFIRMED,
            comment="confirmed on call",
        )
        with uow:
            retrieved = uow.respondents.get(resp.id)
            assert retrieved.selection_status == RespondentStatus.CONFIRMED

    def test_caller_cannot_manually_select_from_pool(self, uow, admin_user, test_assembly):
        caller_id = self._make_caller(uow, admin_user, test_assembly, "caller2@test.com")
        resp = self._create(uow, admin_user, test_assembly, RespondentStatus.POOL)

        with pytest.raises(InsufficientPermissions):
            respondent_service.transition_respondent_status(
                uow,
                caller_id,
                test_assembly.id,
                resp.id,
                new_status=RespondentStatus.SELECTED,
                comment="try override",
            )

    def test_illegal_transition_raises_value_error(self, uow, admin_user, test_assembly):
        resp = self._create(uow, admin_user, test_assembly, RespondentStatus.POOL)
        with pytest.raises(ValueError, match="not allowed"):
            respondent_service.transition_respondent_status(
                uow,
                admin_user.id,
                test_assembly.id,
                resp.id,
                new_status=RespondentStatus.CONFIRMED,
                comment="try",
            )


class TestUpdateRespondent:
    def _create(self, uow, admin_user, assembly):
        return respondent_service.create_respondent(
            uow,
            admin_user.id,
            assembly.id,
            external_id="NB_EDIT",
            attributes={"gender": "Female"},
            email="a@b.com",
            eligible=True,
        )

    def test_round_trips_through_repo(self, uow, admin_user, test_assembly):
        resp = self._create(uow, admin_user, test_assembly)
        respondent_service.update_respondent(
            uow,
            admin_user.id,
            test_assembly.id,
            resp.id,
            comment="fix email",
            email="new@b.com",
        )
        with uow:
            retrieved = uow.respondents.get(resp.id)
            assert retrieved is not None
            assert retrieved.email == "new@b.com"
            assert len(retrieved.comments) == 1
            assert retrieved.comments[0].text == "fix email"

    def test_raises_for_mismatched_assembly(self, uow, admin_user, test_assembly):
        resp = self._create(uow, admin_user, test_assembly)
        other_assembly = Assembly(title="other", question="?", number_to_select=1)
        with uow:
            uow.assemblies.add(other_assembly)
            other_id = other_assembly.id
            uow.commit()
        with pytest.raises(RespondentNotFoundError):
            respondent_service.update_respondent(
                uow,
                admin_user.id,
                other_id,
                resp.id,
                comment="try",
                email="x@y.com",
            )

    def test_refuses_when_permission_denied(self, uow, test_assembly):
        # Create respondent as admin first
        admin = User(email="admin_for_edit@test.com", global_role=GlobalRole.ADMIN, password_hash="h")
        with uow:
            uow.users.add(admin)
            admin_id = admin.id
            uow.commit()
        resp = respondent_service.create_respondent(
            uow, admin_id, test_assembly.id, external_id="NB_PERM", attributes={}
        )

        # Now try with a user with no role
        user = User(email="noedit@test.com", global_role=GlobalRole.USER, password_hash="h")
        with uow:
            uow.users.add(user)
            user_id = user.id
            uow.commit()
        with pytest.raises(InsufficientPermissions):
            respondent_service.update_respondent(uow, user_id, test_assembly.id, resp.id, comment="x", email="z@z.com")

    def test_refuses_on_deleted_status(self, uow, admin_user, test_assembly):
        resp = self._create(uow, admin_user, test_assembly)
        respondent_service.delete_respondent(uow, admin_user.id, test_assembly.id, resp.id, comment="gdpr")
        with pytest.raises(ValueError):
            respondent_service.update_respondent(
                uow,
                admin_user.id,
                test_assembly.id,
                resp.id,
                comment="try",
                email="x@y.com",
            )
