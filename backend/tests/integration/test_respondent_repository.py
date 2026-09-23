"""ABOUTME: Integration tests for SQL-specific RespondentRepository behaviour.
ABOUTME: Tests cascade deletes, JSON serialization, nullable fields, and database constraints."""

import json

import pytest
from sqlalchemy import text
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


class TestRewritingOneAttribute:
    """remove_attribute and rename_attribute rewrite every respondent in one statement."""

    def _add(self, repo, session, assembly, external_id, attributes, **kwargs) -> Respondent:
        respondent = Respondent(assembly_id=assembly.id, external_id=external_id, attributes=attributes, **kwargs)
        repo.add(respondent)
        session.commit()
        return respondent

    def _stored(self, session: Session, respondent: Respondent) -> str:
        """The attributes as the database holds them, key order included."""
        session.expire_all()
        return session.execute(
            text("SELECT attributes::text FROM respondents WHERE id = :id"), {"id": respondent.id}
        ).scalar_one()

    def test_remove_keeps_every_other_key_in_its_place(self, respondent_repo, postgres_session, test_assembly):
        respondent = self._add(
            respondent_repo, postgres_session, test_assembly, "R1", {"zeta": "1", "region": "North", "alpha": "2"}
        )

        changed = respondent_repo.remove_attribute(test_assembly.id, "region")
        postgres_session.commit()

        assert changed == 1
        stored = self._stored(postgres_session, respondent)
        assert list(json.loads(stored)) == ["zeta", "alpha"]

    def test_rename_keeps_the_key_in_its_place(self, respondent_repo, postgres_session, test_assembly):
        respondent = self._add(
            respondent_repo, postgres_session, test_assembly, "R1", {"zeta": "1", "region": "North", "alpha": "2"}
        )

        changed = respondent_repo.rename_attribute(test_assembly.id, "region", "Area")
        postgres_session.commit()

        assert changed == 1
        assert list(json.loads(self._stored(postgres_session, respondent)).items()) == [
            ("zeta", "1"),
            ("Area", "North"),
            ("alpha", "2"),
        ]

    def test_rename_replaces_a_stray_value_under_the_new_key(self, respondent_repo, postgres_session, test_assembly):
        respondent = self._add(
            respondent_repo, postgres_session, test_assembly, "R1", {"Area": "stale", "region": "North"}
        )

        respondent_repo.rename_attribute(test_assembly.id, "region", "Area")
        postgres_session.commit()

        assert json.loads(self._stored(postgres_session, respondent)) == {"Area": "North"}

    def test_only_touches_live_respondents_of_this_assembly_that_have_the_key(
        self, respondent_repo, postgres_session, test_assembly
    ):
        other = Assembly(title="Other", question="Q?")
        postgres_session.add(other)
        postgres_session.commit()
        without = self._add(respondent_repo, postgres_session, test_assembly, "R1", {"gender": "F"})
        deleted = self._add(
            respondent_repo,
            postgres_session,
            test_assembly,
            "R2",
            {"region": "North"},
            selection_status=RespondentStatus.DELETED,
        )
        elsewhere = self._add(respondent_repo, postgres_session, other, "R3", {"region": "North"})

        changed = respondent_repo.remove_attribute(test_assembly.id, "region")
        postgres_session.commit()

        assert changed == 0
        assert json.loads(self._stored(postgres_session, without)) == {"gender": "F"}
        assert json.loads(self._stored(postgres_session, deleted)) == {"region": "North"}
        assert json.loads(self._stored(postgres_session, elsewhere)) == {"region": "North"}

    def test_a_loaded_respondent_sees_the_rewrite_and_its_pending_change_survives(
        self, respondent_repo, postgres_session, test_assembly
    ):
        respondent = self._add(respondent_repo, postgres_session, test_assembly, "R1", {"region": "North"})
        # Loaded and changed in this session, but not yet flushed.
        respondent.attributes = {"region": "North", "gender": "F"}

        respondent_repo.rename_attribute(test_assembly.id, "region", "Area")

        assert respondent.attributes == {"Area": "North", "gender": "F"}
        postgres_session.commit()
        assert json.loads(self._stored(postgres_session, respondent)) == {"Area": "North", "gender": "F"}
