"""ABOUTME: End-to-end PostgreSQL happy-path smokes for the target data sources set-up dialog
ABOUTME: Behavioural coverage (validation, render, transitions) lives in tests/component/"""

import io
from datetime import UTC, datetime

from opendlp.domain.respondent_field_schema import FieldType
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.service_layer import respondent_field_schema_service
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token


def _seed_schema(uow, admin_user, assembly):
    """Seed a schema via CSV import so tests have realistic starting state."""
    import_respondents_from_csv(
        uow,
        admin_user.id,
        assembly.id,
        "external_id,first_name,last_name,gender,postcode\nR001,Alice,Jones,Female,SW1A 1AA\n",
        replace_existing=True,
    )


def _add_target(uow, assembly, name, values):
    category = TargetCategory(
        assembly_id=assembly.id,
        name=name,
        values=[TargetValue(value=value, min=5, max=10) for value in values],
    )
    uow.target_categories.add(category)
    return category.id


def _field(postgres_session_factory, admin_user, assembly, field_key):
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, assembly.id)
        return next(f for f in schema if f.field_key == field_key)


class TestConfigureAgeBrackets:
    def test_age_bracket_round_trip(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        """Set up an age-bracket target from a year of birth, then read the derived field back."""
        # The as-of year must be within a year of today, so never hard-code it.
        this_year = datetime.now(UTC).year
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)
            source = respondent_field_schema_service.add_field(
                uow,
                admin_user.id,
                existing_assembly.id,
                field_key="year_of_birth",
                field_type=FieldType.INTEGER,
            )
            category_id = _add_target(uow, existing_assembly, "age bracket", ["16-24", "25-39", "40+"])

        base = f"/backoffice/assembly/{existing_assembly.id}/target-sources"
        response = logged_in_admin.post(
            f"{base}/{category_id}/configure",
            data={
                "modal": "1",
                "method": "age_bracket",
                "source_mode": "reuse",
                "reuse_field_id": str(source.id),
                "as_of_day": "1",
                "as_of_month": "6",
                "as_of_year": str(this_year),
                "min_age": "16",
                "max_age": "40",
                "boundaries": "25",
                "csrf_token": get_csrf_token(logged_in_admin, base),
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200

        field = _field(postgres_session_factory, admin_user, existing_assembly, "age bracket")
        assert field.is_derived
        assert field.derived_from == ["year_of_birth"]
        assert field.target_category_id == category_id
        assert field.derivation_config["as_of_date"] == f"{this_year}-06-01"
        assert [o.value for o in field.options] == ["under-16", "16-24", "25-39", "40+", "UNKNOWN"]


class TestLookupTable:
    def test_set_up_then_upload_round_trip(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        """Set up a lookup-table target, land on the upload step, upload, and read the rows back."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)
            category_id = _add_target(uow, existing_assembly, "region", ["North", "South"])
        postcode = _field(postgres_session_factory, admin_user, existing_assembly, "postcode")

        base = f"/backoffice/assembly/{existing_assembly.id}/target-sources"
        configure = logged_in_admin.post(
            f"{base}/{category_id}/configure",
            data={
                "modal": "1",
                "method": "large_mapping",
                "source_mode": "reuse",
                "reuse_field_id": str(postcode.id),
                "csrf_token": get_csrf_token(logged_in_admin, base),
            },
            headers={"HX-Request": "true"},
        )
        assert configure.status_code == 200
        assert b"Step 2 of 2" in configure.data

        field = _field(postgres_session_factory, admin_user, existing_assembly, "region")
        csv_content = "postcode,region\nSW1A 1AA,South\nM1 1AE,North\n"
        upload = logged_in_admin.post(
            f"{base}/{category_id}/upload",
            data={
                "setup_step": "1",
                "mapping_file": (io.BytesIO(csv_content.encode("utf-8")), "mapping.csv"),
                "csrf_token": get_csrf_token(logged_in_admin, base),
            },
            content_type="multipart/form-data",
            headers={"HX-Request": "true"},
        )
        assert upload.status_code == 200
        assert b"Rows stored:" in upload.data

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert uow.respondent_field_mapping_entries.count_for_field(field.id) == 2
