"""ABOUTME: End-to-end tests for the respondent field schema management UI
ABOUTME: Covers view, edit label/group, reorder, delete, and initialise flows"""

from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
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

    def test_renders_initialise_button_when_no_schema(self, logged_in_admin, existing_assembly, admin_user):
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        assert b"Initialise empty schema" in response.data

    def test_redirects_when_not_logged_in(self, client, existing_assembly):
        response = client.get(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "login" in response.location


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

    def test_move_up_at_top_is_noop(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow,
                admin_user.id,
                existing_assembly.id,
                "external_id,a,b\nR001,1,2\n",
                replace_existing=True,
            )
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            top = next(f for f in schema if f.field_key == "a")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{top.id}/move",
            data={
                "direction": "up",
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
            after = [f.field_key for f in schema if f.group == RespondentFieldGroup.OTHER]
            assert after == ["a", "b"]


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

    def test_cannot_delete_fixed_field(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            fixed_field = next(f for f in schema if f.is_fixed)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{fixed_field.id}/delete",
            data={
                "csrf_token": get_csrf_token(
                    logged_in_admin,
                    f"/backoffice/assembly/{existing_assembly.id}/respondent-schema",
                ),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        # Fixed field is still there.
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            assert fixed_field.field_key in {f.field_key for f in schema}


class TestManageLayoutLink:
    def test_link_appears_on_data_tab(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=csv")
        assert response.status_code == 200
        assert b"Manage field layout" in response.data


class TestFieldTypeAndOptions:
    def test_schema_page_renders_type_column(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        body = response.data
        assert b"Type" in body
        assert b"Yes / No / Not set" in body  # fixed flags render as BOOL_OR_NONE
        assert b"Email" in body  # email fixed row renders as EMAIL type

    def test_update_accepts_field_type(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            custom = next(f for f in schema if f.field_key == "custom_notes")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{custom.id}/update",
            data={
                "label": custom.label,
                "group": custom.group.value,
                "field_type": FieldType.LONGTEXT.value,
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
            assert field.field_type == FieldType.LONGTEXT

    def test_changing_to_choice_seeds_default_option(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            custom = next(f for f in schema if f.field_key == "custom_notes")

        logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{custom.id}/update",
            data={
                "label": custom.label,
                "group": custom.group.value,
                "field_type": FieldType.CHOICE_RADIO.value,
                "csrf_token": get_csrf_token(
                    logged_in_admin,
                    f"/backoffice/assembly/{existing_assembly.id}/respondent-schema",
                ),
            },
            follow_redirects=False,
        )

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            updated = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            field = next(f for f in updated if f.field_key == "custom_notes")
            assert field.field_type == FieldType.CHOICE_RADIO
            assert field.options is not None
            assert len(field.options) >= 1

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

    def test_remove_option_drops_from_choice_field(
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
                options=[ChoiceOption(value="a"), ChoiceOption(value="b")],
            )

        logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{custom.id}/options/remove",
            data={
                "value": "a",
                "csrf_token": get_csrf_token(
                    logged_in_admin,
                    f"/backoffice/assembly/{existing_assembly.id}/respondent-schema",
                ),
            },
            follow_redirects=False,
        )

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            updated = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            field = next(f for f in updated if f.field_key == "custom_notes")
            assert field.options is not None
            assert [o.value for o in field.options] == ["b"]

    def test_guess_button_shown_when_conditions_met(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        assert b"Guess field types from data" in response.data

    def test_guess_button_hidden_when_no_respondents(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent_field_schema_service.initialise_empty_schema(uow, admin_user.id, existing_assembly.id)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        assert b"Guess field types from data" not in response.data

    def test_guess_button_hidden_when_no_text_fields(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)
            # Flip every non-fixed row away from TEXT so there's nothing to guess.
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            for f in schema:
                if not f.is_fixed and f.field_type == FieldType.TEXT:
                    respondent_field_schema_service.update_field(
                        uow,
                        admin_user.id,
                        existing_assembly.id,
                        f.id,
                        field_type=FieldType.LONGTEXT,
                    )

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        assert b"Guess field types from data" not in response.data

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

    def test_fixed_row_rejects_field_type_change(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _seed_schema(uow, admin_user, existing_assembly)
            schema = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            email_field = next(f for f in schema if f.field_key == "email")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{email_field.id}/update",
            data={
                "label": email_field.label,
                "group": email_field.group.value,
                "field_type": FieldType.TEXT.value,
                "csrf_token": get_csrf_token(
                    logged_in_admin,
                    f"/backoffice/assembly/{existing_assembly.id}/respondent-schema",
                ),
            },
            follow_redirects=False,
        )
        # Redirect back with a flash; type change is silently ignored because is_fixed.
        assert response.status_code == 302

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            updated = respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
            email_field = next(f for f in updated if f.field_key == "email")
            # Still EMAIL — the attempt was refused.
            assert email_field.field_type == FieldType.EMAIL
