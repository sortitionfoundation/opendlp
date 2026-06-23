"""ABOUTME: End-to-end PostgreSQL happy-path smokes for the respondent field schema UI
ABOUTME: Behavioural coverage (validation, render, transitions) lives in tests/component/"""

import pytest

from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldGroup,
)
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
        "external_id,first_name,last_name,gender,postcode,custom_notes\nR001,Alice,Jones,Female,SW1A 1AA,note\n",
        replace_existing=True,
    )


class TestViewSchemaPage:
    def test_renders_for_admin_with_populated_schema(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        body = response.data
        # Group headings surface.
        assert b"Name and contact" in body
        assert b"About you" in body
        # Custom CSV column appears somewhere on the page.
        assert b"custom_notes" in body
        # Fixed fields render their "Fixed" tag.
        assert b"Fixed" in body
        # Initialise button is not shown when schema already exists.
        assert b"Initialise empty schema" not in body


class TestInitialiseSchema:
    def test_initialise_creates_fixed_rows(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/initialise",
            data={
                "csrf_token": get_csrf_token(
                    logged_in_admin,
                    f"/backoffice/assembly/{existing_assembly.id}/respondent-schema",
                ),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            assert len(schema) > 0
            assert all(f.is_fixed for f in schema)


class TestUpdateField:
    def test_updates_label_and_group(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            custom_field = next(f for f in schema if f.field_key == "custom_notes")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{custom_field.id}/update",
            data={
                "label": "Notes from organiser",
                "group": RespondentFieldGroup.ABOUT_YOU.value,
                "csrf_token": get_csrf_token(
                    logged_in_admin,
                    f"/backoffice/assembly/{existing_assembly.id}/respondent-schema",
                ),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            updated = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            moved = next(f for f in updated if f.field_key == "custom_notes")
            assert moved.label == "Notes from organiser"
            assert moved.group == RespondentFieldGroup.ABOUT_YOU


class TestMoveField:
    @pytest.mark.db_semantics
    def test_move_up_swaps_with_previous_field(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow,
                admin_user.id,
                existing_assembly.id,
                "external_id,a,b,c\nR001,1,2,3\n",
                replace_existing=True,
            )
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            others = [f for f in schema if f.group == RespondentFieldGroup.OTHER]
            assert [f.field_key for f in others] == ["a", "b", "c"]
            field_b_id = others[1].id

        logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{field_b_id}/move",
            data={
                "direction": "up",
                "csrf_token": get_csrf_token(
                    logged_in_admin,
                    f"/backoffice/assembly/{existing_assembly.id}/respondent-schema",
                ),
            },
            follow_redirects=False,
        )

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            after = [f.field_key for f in schema if f.group == RespondentFieldGroup.OTHER]
            assert after == ["b", "a", "c"]


class TestAddField:
    def test_add_field_creates_row(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/add",
            data={
                "field_key": "Age Range",
                "label": "Age range",
                "group": RespondentFieldGroup.ABOUT_YOU.value,
                "field_type": FieldType.TEXT.value,
                "on_registration_page": FieldOnRegistrationPage.YES_OPTIONAL.value,
                "csrf_token": get_csrf_token(
                    logged_in_admin,
                    f"/backoffice/assembly/{existing_assembly.id}/respondent-schema",
                ),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            # The submitted "Age Range" is normalised to a name-attribute-safe key.
            added = next(f for f in schema if f.field_key == "age_range")
            assert added.label == "Age range"
            assert added.group == RespondentFieldGroup.ABOUT_YOU
            assert added.field_type == FieldType.TEXT
            assert added.on_registration_page == FieldOnRegistrationPage.YES_OPTIONAL


class TestDeleteField:
    def test_delete_non_fixed_field(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            custom_field = next(f for f in schema if f.field_key == "custom_notes")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{custom_field.id}/delete",
            data={
                "csrf_token": get_csrf_token(
                    logged_in_admin,
                    f"/backoffice/assembly/{existing_assembly.id}/respondent-schema",
                ),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            assert "custom_notes" not in {f.field_key for f in schema}


class TestFieldTypeAndOptions:
    def test_add_option_appends_to_choice_field(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            custom = next(f for f in schema if f.field_key == "custom_notes")
            respondent_field_schema_service.update_field(
                uow,
                admin_user.id,
                existing_assembly.id,
                custom.id,
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="initial")],
            )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{custom.id}/options/add",
            data={
                "value": "second",
                "help_text": "second option",
                "csrf_token": get_csrf_token(
                    logged_in_admin,
                    f"/backoffice/assembly/{existing_assembly.id}/respondent-schema",
                ),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            updated = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            field = next(f for f in updated if f.field_key == "custom_notes")
            assert field.options is not None
            assert [o.value for o in field.options] == ["initial", "second"]
            assert field.options[1].help_text == "second option"

    def test_guess_post_round_trips_and_flashes(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow,
                admin_user.id,
                existing_assembly.id,
                "external_id,voted\nR1,true\nR2,false\n",
                replace_existing=True,
            )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/guess-types",
            data={
                "csrf_token": get_csrf_token(
                    logged_in_admin,
                    f"/backoffice/assembly/{existing_assembly.id}/respondent-schema",
                ),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            voted = next(f for f in schema if f.field_key == "voted")
            assert voted.field_type == FieldType.BOOL_OR_NONE
