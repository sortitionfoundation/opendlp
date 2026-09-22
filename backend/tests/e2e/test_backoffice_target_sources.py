"""ABOUTME: End-to-end PostgreSQL happy-path smokes for the target data sources set-up dialog
ABOUTME: Behavioural coverage (validation, render, transitions) lives in tests/component/"""

import io
from datetime import UTC, datetime

from opendlp.domain.respondent_field_schema import ChoiceOption, FieldType
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.service_layer import respondent_field_schema_service, target_service
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


def _csrf(client, assembly):
    return get_csrf_token(client, f"/backoffice/assembly/{assembly.id}/target-sources")


class TestPagesRender:
    def test_the_checklist_and_set_up_dialog_render(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)
            category_id = _add_target(uow, existing_assembly, "Region", ["North", "South"])

        base = f"/backoffice/assembly/{existing_assembly.id}/target-sources"
        page = logged_in_admin.get(base)
        dialog = logged_in_admin.get(f"{base}/{category_id}/setup-modal", headers={"HX-Request": "true"})

        assert page.status_code == 200
        assert b"Region" in page.data
        assert dialog.status_code == 200
        assert b"Set up data source for Region" in dialog.data


class TestExactCopyLifecycle:
    def test_adopt_resync_then_unlink(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        """Link a name-matched question, follow a new target value, then let the question go."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)
            question = respondent_field_schema_service.add_field(
                uow,
                admin_user.id,
                existing_assembly.id,
                field_key="Tenure",
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="Own"), ChoiceOption(value="Rent")],
            )
            category_id = _add_target(uow, existing_assembly, "Tenure", ["Own", "Rent"])
        base = f"/backoffice/assembly/{existing_assembly.id}/target-sources"

        adopt = logged_in_admin.post(
            f"{base}/{category_id}/adopt",
            data={"field_id": str(question.id), "csrf_token": _csrf(logged_in_admin, existing_assembly)},
            headers={"HX-Request": "true"},
        )
        assert adopt.status_code == 200
        assert _field(postgres_session_factory, admin_user, existing_assembly, "Tenure").target_category_id == (
            category_id
        )

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            target_service.add_target_value(
                uow, admin_user.id, existing_assembly.id, category_id, "Other", min_count=0, max_count=5
            )
            uow.commit()
        resync = logged_in_admin.post(
            f"{base}/{category_id}/resync",
            data={"csrf_token": _csrf(logged_in_admin, existing_assembly)},
            headers={"HX-Request": "true"},
        )
        assert resync.status_code == 200
        field = _field(postgres_session_factory, admin_user, existing_assembly, "Tenure")
        assert [o.value for o in field.options] == ["Own", "Rent", "Other"]

        unlink = logged_in_admin.post(
            f"{base}/{category_id}/unlink",
            data={"csrf_token": _csrf(logged_in_admin, existing_assembly)},
            headers={"HX-Request": "true"},
        )
        assert unlink.status_code == 200
        field = _field(postgres_session_factory, admin_user, existing_assembly, "Tenure")
        assert field.target_category_id is None


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

        upload_dialog = logged_in_admin.get(f"{base}/{category_id}/upload-modal", headers={"HX-Request": "true"})
        assert upload_dialog.status_code == 200
        assert b"Upload lookup table" in upload_dialog.data

        recompute = logged_in_admin.post(
            f"{base}/{category_id}/recompute",
            data={"csrf_token": get_csrf_token(logged_in_admin, base)},
            headers={"HX-Request": "true"},
        )
        assert recompute.status_code == 200
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = uow.respondents.get_by_external_id(existing_assembly.id, "R001")
            assert respondent.attributes["region"] == "South"
