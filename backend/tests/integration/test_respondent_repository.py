"""ABOUTME: Integration tests for SQL-specific RespondentRepository behaviour.
ABOUTME: Tests cascade deletes, JSON serialization, nullable fields, and database constraints."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opendlp.adapters.sql_repository import SqlAlchemyRespondentRepository
from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent


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
