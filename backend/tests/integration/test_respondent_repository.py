"""ABOUTME: Integration tests for RespondentRepository
ABOUTME: Tests respondent repository methods with actual database operations"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opendlp.adapters.sql_repository import SqlAlchemyRespondentRepository
from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import RespondentStatus


@pytest.fixture
def respondent_repo(postgres_session):
    """Create a RespondentRepository."""
    return SqlAlchemyRespondentRepository(postgres_session)


@pytest.fixture
def test_assembly(postgres_session):
    """Create a test assembly."""
    assembly = Assembly(title="Test Assembly", question="Test?", number_to_select=30)
    postgres_session.add(assembly)
    postgres_session.commit()
    return assembly


class TestRespondentRepository:
    def test_add_and_get_respondent(
        self, respondent_repo: SqlAlchemyRespondentRepository, test_assembly: Assembly, postgres_session: Session
    ):
        """Test adding and retrieving a respondent."""
        resp = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB001",
            attributes={"Gender": "Female", "Age": "30-44"},
            email="alice@test.com",
            eligible=True,
            can_attend=True,
        )

        respondent_repo.add(resp)
        postgres_session.commit()

        # Test get by ID
        retrieved = respondent_repo.get(resp.id)
        assert retrieved is not None
        assert retrieved.external_id == "NB001"
        assert retrieved.attributes["Gender"] == "Female"
        assert retrieved.email == "alice@test.com"
        assert retrieved.eligible is True
        assert retrieved.can_attend is True

    def test_get_by_external_id(
        self, respondent_repo: SqlAlchemyRespondentRepository, test_assembly: Assembly, postgres_session: Session
    ):
        """Test retrieving respondent by external ID."""
        resp = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB001",
            attributes={"Gender": "Female"},
        )

        respondent_repo.add(resp)
        postgres_session.commit()

        # Test get by external_id
        retrieved = respondent_repo.get_by_external_id(test_assembly.id, "NB001")
        assert retrieved is not None
        assert retrieved.id == resp.id

        # Test non-existent external_id
        assert respondent_repo.get_by_external_id(test_assembly.id, "NB999") is None

    def test_get_by_assembly_id(
        self, respondent_repo: SqlAlchemyRespondentRepository, test_assembly: Assembly, postgres_session: Session
    ):
        """Test retrieving respondents by assembly ID."""
        resp1 = Respondent(assembly_id=test_assembly.id, external_id="NB001")
        resp2 = Respondent(assembly_id=test_assembly.id, external_id="NB002")

        respondent_repo.add(resp1)
        respondent_repo.add(resp2)
        postgres_session.commit()

        # Get all respondents for assembly
        respondents = respondent_repo.get_by_assembly_id(test_assembly.id)
        assert len(respondents) == 2

    def test_get_by_assembly_id_with_status_filter(
        self, respondent_repo: SqlAlchemyRespondentRepository, test_assembly: Assembly, postgres_session: Session
    ):
        """Test filtering respondents by status."""
        resp1 = Respondent(assembly_id=test_assembly.id, external_id="NB001", selection_status=RespondentStatus.POOL)
        resp2 = Respondent(
            assembly_id=test_assembly.id, external_id="NB002", selection_status=RespondentStatus.SELECTED
        )

        respondent_repo.add(resp1)
        respondent_repo.add(resp2)
        postgres_session.commit()

        # Filter by status
        pool_only = respondent_repo.get_by_assembly_id(test_assembly.id, status=RespondentStatus.POOL)
        assert len(pool_only) == 1
        assert pool_only[0].external_id == "NB001"

        selected_only = respondent_repo.get_by_assembly_id(test_assembly.id, status=RespondentStatus.SELECTED)
        assert len(selected_only) == 1
        assert selected_only[0].external_id == "NB002"

    def test_get_by_assembly_id_with_eligible_filter(
        self, respondent_repo: SqlAlchemyRespondentRepository, test_assembly: Assembly, postgres_session: Session
    ):
        """Test filtering respondents by eligibility."""
        resp1 = Respondent(assembly_id=test_assembly.id, external_id="NB001", eligible=True, can_attend=True)
        resp2 = Respondent(assembly_id=test_assembly.id, external_id="NB002", eligible=False, can_attend=True)
        resp3 = Respondent(assembly_id=test_assembly.id, external_id="NB003", eligible=True, can_attend=False)

        respondent_repo.add(resp1)
        respondent_repo.add(resp2)
        respondent_repo.add(resp3)
        postgres_session.commit()

        # Filter by eligible_only
        eligible_only = respondent_repo.get_by_assembly_id(test_assembly.id, eligible_only=True)
        assert len(eligible_only) == 1
        assert eligible_only[0].external_id == "NB001"

    def test_count_available_for_selection(
        self, respondent_repo: SqlAlchemyRespondentRepository, test_assembly: Assembly, postgres_session: Session
    ):
        """Test counting respondents available for selection."""
        # Available: POOL, eligible=True, can_attend=True
        resp1 = Respondent(assembly_id=test_assembly.id, external_id="NB001", eligible=True, can_attend=True)

        # Not available: eligible=False
        resp2 = Respondent(assembly_id=test_assembly.id, external_id="NB002", eligible=False, can_attend=True)

        # Not available: can_attend=False
        resp3 = Respondent(assembly_id=test_assembly.id, external_id="NB003", eligible=True, can_attend=False)

        # Not available: status=SELECTED
        resp4 = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB004",
            eligible=True,
            can_attend=True,
            selection_status=RespondentStatus.SELECTED,
        )

        respondent_repo.add(resp1)
        respondent_repo.add(resp2)
        respondent_repo.add(resp3)
        respondent_repo.add(resp4)
        postgres_session.commit()

        count = respondent_repo.count_available_for_selection(test_assembly.id)
        assert count == 1

    def test_bulk_add(
        self, respondent_repo: SqlAlchemyRespondentRepository, test_assembly: Assembly, postgres_session: Session
    ):
        """Test bulk adding respondents."""
        respondents = [
            Respondent(assembly_id=test_assembly.id, external_id=f"NB{i:03d}", attributes={"index": str(i)})
            for i in range(100)
        ]

        respondent_repo.bulk_add(respondents)
        postgres_session.commit()

        # Verify all were added
        all_resp = respondent_repo.get_by_assembly_id(test_assembly.id)
        assert len(all_resp) == 100

    def test_delete_respondent(
        self, respondent_repo: SqlAlchemyRespondentRepository, test_assembly: Assembly, postgres_session: Session
    ):
        """Test deleting a respondent."""
        resp = Respondent(assembly_id=test_assembly.id, external_id="NB001")

        respondent_repo.add(resp)
        postgres_session.commit()
        resp_id = resp.id

        # Delete the respondent
        r = respondent_repo.get(resp_id)
        respondent_repo.delete(r)
        postgres_session.commit()

        # Verify it's gone
        retrieved = respondent_repo.get(resp_id)
        assert retrieved is None

    def test_cascade_delete_with_assembly(
        self, respondent_repo: SqlAlchemyRespondentRepository, postgres_session: Session
    ):
        """Test that respondents are deleted when assembly is deleted (cascade)."""
        # Create assembly
        assembly = Assembly(title="Test", question="Q?")
        postgres_session.add(assembly)
        postgres_session.commit()
        assembly_id = assembly.id

        # Create respondent
        resp = Respondent(assembly_id=assembly_id, external_id="NB001")
        respondent_repo.add(resp)
        postgres_session.commit()
        resp_id = resp.id

        # Delete assembly
        postgres_session.delete(assembly)
        postgres_session.commit()

        # Respondent should be gone (cascade delete)
        respondent = respondent_repo.get(resp_id)
        assert respondent is None

    def test_attributes_json_serialization(
        self, respondent_repo: SqlAlchemyRespondentRepository, test_assembly: Assembly, postgres_session: Session
    ):
        """Test that attributes dict is properly serialized/deserialized from JSON."""
        resp = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB001",
            attributes={"Gender": "Female", "Age": "30-44", "PostalCode": "SW1A 1AA"},
        )

        respondent_repo.add(resp)
        postgres_session.commit()

        # Retrieve and verify attributes survived serialization
        retrieved = respondent_repo.get(resp.id)
        assert retrieved is not None
        assert retrieved.attributes["Gender"] == "Female"
        assert retrieved.attributes["Age"] == "30-44"
        assert retrieved.attributes["PostalCode"] == "SW1A 1AA"

    def test_nullable_boolean_fields(
        self, respondent_repo: SqlAlchemyRespondentRepository, test_assembly: Assembly, postgres_session: Session
    ):
        """Test that boolean fields can be None."""
        resp = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB001",
            consent=None,
            eligible=None,
            can_attend=None,
        )

        respondent_repo.add(resp)
        postgres_session.commit()

        # Retrieve and verify None values preserved
        retrieved = respondent_repo.get(resp.id)
        assert retrieved is not None
        assert retrieved.consent is None
        assert retrieved.eligible is None
        assert retrieved.can_attend is None

    def test_unique_constraint_assembly_external_id(
        self, respondent_repo: SqlAlchemyRespondentRepository, test_assembly: Assembly, postgres_session: Session
    ):
        """Test that external_id must be unique per assembly."""
        resp1 = Respondent(assembly_id=test_assembly.id, external_id="NB001")
        respondent_repo.add(resp1)
        postgres_session.commit()

        # Try to add another respondent with same external_id
        resp2 = Respondent(assembly_id=test_assembly.id, external_id="NB001")
        respondent_repo.add(resp2)

        # This should raise an integrity error
        with pytest.raises(IntegrityError):  # IntegrityError from database
            postgres_session.commit()
