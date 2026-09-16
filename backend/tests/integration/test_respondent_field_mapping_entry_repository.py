"""ABOUTME: Integration tests for the SQL RespondentFieldMappingEntryRepository against PostgreSQL.
ABOUTME: Covers the unique (field_id, lookup_key) index, cascade on field delete and the bulk insert path."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opendlp.adapters.sql_repository import (
    SqlAlchemyRespondentFieldDefinitionRepository,
    SqlAlchemyRespondentFieldMappingEntryRepository,
)
from opendlp.domain.assembly import Assembly
from opendlp.domain.respondent_field_schema import (
    RespondentFieldDefinition,
    RespondentFieldGroup,
    RespondentFieldMappingEntry,
)


@pytest.fixture
def mapping_repo(postgres_session: Session) -> SqlAlchemyRespondentFieldMappingEntryRepository:
    return SqlAlchemyRespondentFieldMappingEntryRepository(postgres_session)


@pytest.fixture
def region_field(postgres_session: Session) -> RespondentFieldDefinition:
    assembly = Assembly(title="Test Assembly", question="Q?", number_to_select=30)
    postgres_session.add(assembly)
    postgres_session.commit()
    field = RespondentFieldDefinition(
        assembly_id=assembly.id,
        field_key=f"region_{uuid.uuid4().hex[:6]}",
        label="Region",
        group=RespondentFieldGroup.DERIVED,
        sort_order=10,
    )
    postgres_session.add(field)
    postgres_session.commit()
    return field


@pytest.mark.db_semantics
class TestMappingEntryDbSemantics:
    def test_duplicate_lookup_key_for_one_field_is_rejected(
        self,
        mapping_repo: SqlAlchemyRespondentFieldMappingEntryRepository,
        region_field: RespondentFieldDefinition,
        postgres_session: Session,
    ) -> None:
        mapping_repo.add(
            RespondentFieldMappingEntry(field_id=region_field.id, lookup_key="SW1A1AA", output_value="London")
        )
        mapping_repo.add(
            RespondentFieldMappingEntry(field_id=region_field.id, lookup_key="SW1A1AA", output_value="South")
        )

        with pytest.raises(IntegrityError):
            postgres_session.commit()
        postgres_session.rollback()

    def test_deleting_the_field_cascades_to_its_entries(
        self,
        mapping_repo: SqlAlchemyRespondentFieldMappingEntryRepository,
        region_field: RespondentFieldDefinition,
        postgres_session: Session,
    ) -> None:
        mapping_repo.bulk_add([
            RespondentFieldMappingEntry(field_id=region_field.id, lookup_key="SW1A1AA", output_value="London"),
            RespondentFieldMappingEntry(field_id=region_field.id, lookup_key="M11AE", output_value="North"),
        ])
        postgres_session.commit()
        assert mapping_repo.count_for_field(region_field.id) == 2

        SqlAlchemyRespondentFieldDefinitionRepository(postgres_session).delete(region_field)
        postgres_session.commit()

        assert mapping_repo.count_for_field(region_field.id) == 0

    def test_bulk_add_rows_are_readable_through_the_repository(
        self,
        mapping_repo: SqlAlchemyRespondentFieldMappingEntryRepository,
        region_field: RespondentFieldDefinition,
        postgres_session: Session,
    ) -> None:
        entries = [
            RespondentFieldMappingEntry(field_id=region_field.id, lookup_key=f"KEY{i:05d}", output_value="North")
            for i in range(12_000)
        ]
        mapping_repo.bulk_add(entries)
        postgres_session.commit()

        assert mapping_repo.count_for_field(region_field.id) == 12_000
        found = mapping_repo.get_many(region_field.id, ["KEY00000", "KEY11999", "MISSING"])
        assert {(e.lookup_key, e.output_value) for e in found} == {("KEY00000", "North"), ("KEY11999", "North")}
        assert mapping_repo.get(entries[7].id) is not None
