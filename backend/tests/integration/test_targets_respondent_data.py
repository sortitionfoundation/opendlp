"""ABOUTME: Integration tests for respondent data on the targets page
ABOUTME: Tests repository methods, service functions, and new endpoints for respondent-aware target features"""

import uuid

import pytest
from sqlalchemy.orm import Session

from opendlp.adapters.sql_repository import SqlAlchemyRespondentRepository
from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.flask_app import create_app
from opendlp.service_layer import assembly_service
from opendlp.service_layer.respondent_service import (
    get_respondent_attribute_value_counts,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.fakes import FakeRespondentRepository

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def respondent_repo(postgres_session: Session) -> SqlAlchemyRespondentRepository:
    return SqlAlchemyRespondentRepository(postgres_session)


@pytest.fixture
def test_assembly(postgres_session: Session) -> Assembly:
    assembly = Assembly(title="Test Assembly", question="Test?", number_to_select=30)
    postgres_session.add(assembly)
    postgres_session.commit()
    return assembly


@pytest.fixture
def uow(postgres_session_factory) -> SqlAlchemyUnitOfWork:  # type: ignore[no-untyped-def]
    return SqlAlchemyUnitOfWork(postgres_session_factory)


@pytest.fixture
def admin_user(uow: SqlAlchemyUnitOfWork) -> User:
    user = User(email="admin@test.com", global_role=GlobalRole.ADMIN, password_hash="hash123")
    with uow:
        uow.users.add(user)
        detached = user.create_detached_copy()
        uow.commit()
        return detached


# ── Repository Tests ──────────────────────────────────────────


class TestGetAttributeValueCounts:
    def test_counts_by_attribute(
        self,
        respondent_repo: SqlAlchemyRespondentRepository,
        test_assembly: Assembly,
        postgres_session: Session,
    ) -> None:
        """Returns correct counts for each distinct value of an attribute."""
        for ext_id, gender in [("1", "Male"), ("2", "Male"), ("3", "Female"), ("4", "Female"), ("5", "Female")]:
            respondent_repo.add(
                Respondent(assembly_id=test_assembly.id, external_id=ext_id, attributes={"Gender": gender})
            )
        postgres_session.commit()

        counts = respondent_repo.get_attribute_value_counts(test_assembly.id, "Gender")
        assert counts == {"Male": 2, "Female": 3}

    def test_empty_when_no_respondents(
        self,
        respondent_repo: SqlAlchemyRespondentRepository,
        test_assembly: Assembly,
    ) -> None:
        """Returns empty dict when there are no respondents."""
        counts = respondent_repo.get_attribute_value_counts(test_assembly.id, "Gender")
        assert counts == {}

    def test_empty_when_attribute_not_present(
        self,
        respondent_repo: SqlAlchemyRespondentRepository,
        test_assembly: Assembly,
        postgres_session: Session,
    ) -> None:
        """Returns empty dict when the attribute does not exist in respondent data."""
        respondent_repo.add(Respondent(assembly_id=test_assembly.id, external_id="1", attributes={"Gender": "Male"}))
        postgres_session.commit()

        counts = respondent_repo.get_attribute_value_counts(test_assembly.id, "NonExistent")
        assert counts == {}

    def test_counts_scoped_to_assembly(
        self,
        respondent_repo: SqlAlchemyRespondentRepository,
        test_assembly: Assembly,
        postgres_session: Session,
    ) -> None:
        """Counts are scoped to a specific assembly, not global."""
        other_assembly = Assembly(title="Other", question="Q?", number_to_select=10)
        postgres_session.add(other_assembly)
        postgres_session.commit()

        respondent_repo.add(Respondent(assembly_id=test_assembly.id, external_id="1", attributes={"Age": "18-25"}))
        respondent_repo.add(Respondent(assembly_id=other_assembly.id, external_id="2", attributes={"Age": "26-35"}))
        postgres_session.commit()

        counts = respondent_repo.get_attribute_value_counts(test_assembly.id, "Age")
        assert counts == {"18-25": 1}

    def test_multiple_attributes(
        self,
        respondent_repo: SqlAlchemyRespondentRepository,
        test_assembly: Assembly,
        postgres_session: Session,
    ) -> None:
        """Can query different attributes independently."""
        respondent_repo.add(
            Respondent(
                assembly_id=test_assembly.id,
                external_id="1",
                attributes={"Gender": "Male", "Age": "18-25"},
            )
        )
        respondent_repo.add(
            Respondent(
                assembly_id=test_assembly.id,
                external_id="2",
                attributes={"Gender": "Female", "Age": "18-25"},
            )
        )
        postgres_session.commit()

        gender_counts = respondent_repo.get_attribute_value_counts(test_assembly.id, "Gender")
        assert gender_counts == {"Male": 1, "Female": 1}

        age_counts = respondent_repo.get_attribute_value_counts(test_assembly.id, "Age")
        assert age_counts == {"18-25": 2}


# ── Service Layer Tests ───────────────────────────────────────


class TestGetRespondentAttributeValueCountsService:
    def test_delegates_to_repository(
        self,
        uow: SqlAlchemyUnitOfWork,
        admin_user: User,
    ) -> None:
        """Service function returns value counts from the repository."""
        assembly = Assembly(title="Svc Test", question="Q?", number_to_select=10)
        with uow:
            uow.assemblies.add(assembly)
            assembly_id = assembly.id
            uow.respondents.add(Respondent(assembly_id=assembly_id, external_id="1", attributes={"Region": "North"}))
            uow.respondents.add(Respondent(assembly_id=assembly_id, external_id="2", attributes={"Region": "North"}))
            uow.respondents.add(Respondent(assembly_id=assembly_id, external_id="3", attributes={"Region": "South"}))
            uow.commit()

        uow2 = SqlAlchemyUnitOfWork(uow.session_factory)
        with uow2:
            counts = get_respondent_attribute_value_counts(uow2, assembly_id, "Region")
        assert counts == {"North": 2, "South": 1}


# ── Fake Repository Tests ────────────────────────────────────


class TestFakeRespondentRepositoryValueCounts:
    def test_counts_by_attribute(self) -> None:
        """Fake repository correctly counts attribute values."""
        repo = FakeRespondentRepository()
        aid = uuid.uuid4()
        repo.add(Respondent(assembly_id=aid, external_id="1", attributes={"Color": "Red"}))
        repo.add(Respondent(assembly_id=aid, external_id="2", attributes={"Color": "Red"}))
        repo.add(Respondent(assembly_id=aid, external_id="3", attributes={"Color": "Blue"}))

        counts = repo.get_attribute_value_counts(aid, "Color")
        assert counts == {"Red": 2, "Blue": 1}

    def test_empty_for_missing_attribute(self) -> None:
        """Fake repository returns empty dict for non-existent attribute."""
        repo = FakeRespondentRepository()
        aid = uuid.uuid4()
        repo.add(Respondent(assembly_id=aid, external_id="1", attributes={"Color": "Red"}))

        counts = repo.get_attribute_value_counts(aid, "Size")
        assert counts == {}


# ── Endpoint Tests ────────────────────────────────────────────


class TestAddMissingValuesEndpoint:
    def test_requires_login(self) -> None:
        app = create_app("testing")
        client = app.test_client()
        assembly_id = uuid.uuid4()
        category_id = uuid.uuid4()
        response = client.post(f"/assemblies/{assembly_id}/targets/categories/{category_id}/values/add-missing")
        assert response.status_code == 302
        assert "/auth/login" in response.location


class TestAddCategoriesFromColumnsEndpoint:
    def test_requires_login(self) -> None:
        app = create_app("testing")
        client = app.test_client()
        assembly_id = uuid.uuid4()
        response = client.post(f"/assemblies/{assembly_id}/targets/categories/add-from-columns")
        assert response.status_code == 302
        assert "/auth/login" in response.location


# ── Target Category with Respondent Count Integration ─────────


class TestTargetCategoryRespondentCounts:
    def test_build_respondent_counts_for_matching_category(
        self,
        uow: SqlAlchemyUnitOfWork,
        admin_user: User,
    ) -> None:
        """When a target category name matches a respondent attribute, counts are returned."""
        assembly = Assembly(title="Counts Test", question="Q?", number_to_select=10)
        with uow:
            uow.assemblies.add(assembly)
            assembly_id = assembly.id
            uow.respondents.add(Respondent(assembly_id=assembly_id, external_id="1", attributes={"Gender": "Male"}))
            uow.respondents.add(Respondent(assembly_id=assembly_id, external_id="2", attributes={"Gender": "Female"}))
            uow.respondents.add(Respondent(assembly_id=assembly_id, external_id="3", attributes={"Gender": "Female"}))
            uow.commit()

        # Create a target category matching the attribute name
        uow2 = SqlAlchemyUnitOfWork(uow.session_factory)
        assembly_service.create_target_category(uow2, admin_user.id, assembly_id, name="Gender")

        # Verify that repository returns correct columns and counts
        uow3 = SqlAlchemyUnitOfWork(uow.session_factory)
        with uow3:
            columns = uow3.respondents.get_attribute_columns(assembly_id)
            counts = uow3.respondents.get_attribute_value_counts(assembly_id, "Gender")

        assert "Gender" in columns
        assert counts == {"Male": 1, "Female": 2}
