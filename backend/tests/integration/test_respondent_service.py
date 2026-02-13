"""ABOUTME: Integration tests for respondent service functions
ABOUTME: Tests respondent creation, CSV import, and retrieval service functions"""

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, RespondentStatus
from opendlp.service_layer import respondent_service
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


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

        respondents, errors = respondent_service.import_respondents_from_csv(
            uow, admin_user.id, test_assembly.id, csv_content
        )

        assert len(respondents) == 2
        assert respondents[0].external_id == "NB001"
        assert respondents[0].attributes["Gender"] == "Female"
        assert respondents[0].email == "alice@test.com"
        assert len(errors) == 0

        # Verify they were persisted
        with uow:
            all_resp = uow.respondents.get_by_assembly_id(test_assembly.id)
            assert len(all_resp) == 2

    def test_import_csv_without_external_id_column(self, uow, admin_user: User, test_assembly: Assembly):
        """Test importing CSV without external_id column raises error."""
        csv_content = """name,age
Alice,30"""

        with pytest.raises(InvalidSelection, match="must have 'external_id' column"):
            respondent_service.import_respondents_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

    def test_import_skips_duplicates(self, uow, admin_user: User, test_assembly: Assembly):
        """Test importing CSV with duplicates skips them."""
        csv_content = """external_id,Gender
NB001,Female
NB001,Male"""

        respondents, errors = respondent_service.import_respondents_from_csv(
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

        respondents, errors = respondent_service.import_respondents_from_csv(
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

        respondents, errors = respondent_service.import_respondents_from_csv(
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

        respondents, errors = respondent_service.import_respondents_from_csv(
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

        respondents, errors = respondent_service.import_respondents_from_csv(
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
