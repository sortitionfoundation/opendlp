# ABOUTME: Component tests for the respondent field schema management UI over a FakeUnitOfWork
# ABOUTME: Drives the real backoffice schema routes + services against a seeded fake store (no PostgreSQL)

from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldGroup,
)
from opendlp.service_layer import respondent_field_schema_service
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from tests.fakes import FakeUnitOfWork


def _seed_schema(fake_store, admin_user, assembly):
    """Seed a schema via CSV import so tests have realistic starting state."""
    with FakeUnitOfWork(store=fake_store) as uow:
        import_respondents_from_csv(
            uow,
            admin_user.id,
            assembly.id,
            "external_id,first_name,last_name,gender,postcode,custom_notes\nR001,Alice,Jones,Female,SW1A 1AA,note\n",
            replace_existing=True,
        )


def _get_schema(fake_store, admin_user, assembly):
    with FakeUnitOfWork(store=fake_store) as uow:
        return respondent_field_schema_service.get_schema(uow, admin_user.id, assembly.id)


class TestViewSchemaPage:
    def test_redirects_when_not_logged_in(self, client, existing_assembly):
        response = client.get(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "login" in response.location

    def test_renders_initialise_button_when_no_schema(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        assert b"Initialise empty schema" in response.data


class TestOnRegistrationPage:
    def test_schema_page_renders_registration_column(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "On registration form" in body
        assert 'name="on_registration_page"' in body

    def test_update_sets_on_registration_page(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom_field = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{custom_field.id}/update",
            data={
                "label": "Custom notes",
                "on_registration_page": FieldOnRegistrationPage.NO.value,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes")
        assert field.on_registration_page == FieldOnRegistrationPage.NO


class TestMoveField:
    def test_move_up_at_top_is_noop(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        with FakeUnitOfWork(store=fake_store) as uow:
            import_respondents_from_csv(
                uow,
                admin_user.id,
                existing_assembly.id,
                "external_id,a,b\nR001,1,2\n",
                replace_existing=True,
            )
        top = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "a")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{top.id}/move",
            data={"direction": "up"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        after = [
            f.field_key
            for f in _get_schema(fake_store, admin_user, existing_assembly)
            if f.group == RespondentFieldGroup.OTHER
        ]
        assert after == ["a", "b"]


class TestAddField:
    def test_add_choice_field_seeds_placeholder_option(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/add",
            data={
                "field_key": "preferred_contact",
                "field_type": FieldType.CHOICE_RADIO.value,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        added = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "preferred_contact"
        )
        assert added.field_type == FieldType.CHOICE_RADIO
        assert [opt.value for opt in added.options] == ["option_1"]

    def test_add_duplicate_key_is_rejected(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)
        before = len(_get_schema(fake_store, admin_user, existing_assembly))

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/add",
            data={"field_key": "custom_notes"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"already exists" in response.data

        after = len(_get_schema(fake_store, admin_user, existing_assembly))
        assert after == before

    def test_add_empty_key_is_rejected(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)
        before = len(_get_schema(fake_store, admin_user, existing_assembly))

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/add",
            data={"field_key": "!!!"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        after = len(_get_schema(fake_store, admin_user, existing_assembly))
        assert after == before

    def test_add_form_renders_when_schema_exists(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        assert b"Add a field" in response.data
        assert f"/assembly/{existing_assembly.id}/respondent-schema/fields/add".encode() in response.data

    def test_add_form_absent_without_schema(self, logged_in_admin, existing_assembly):
        # No schema yet: the Initialise prompt shows instead of the add form.
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        assert b"Add a field" not in response.data


class TestDeleteField:
    def test_cannot_delete_fixed_field(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)
        fixed_field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.is_fixed)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{fixed_field.id}/delete",
            data={},
            follow_redirects=True,
        )
        assert response.status_code == 200

        schema = _get_schema(fake_store, admin_user, existing_assembly)
        assert fixed_field.field_key in {f.field_key for f in schema}


class TestFieldsTab:
    def test_fields_tab_appears_in_assembly_tab_bar(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=csv")
        assert response.status_code == 200
        assert f"/assembly/{existing_assembly.id}/respondent-schema".encode() in response.data

    def test_fields_tab_is_never_disabled(self, logged_in_admin, existing_assembly):
        # Visit the Data tab before any data source is chosen — the Fields tab
        # must still be a live link, not a disabled placeholder.
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data")
        assert response.status_code == 200
        assert f"/assembly/{existing_assembly.id}/respondent-schema".encode() in response.data


class TestFieldTypeAndOptions:
    def test_schema_page_renders_type_column(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        body = response.data
        assert b"Type" in body
        assert b"Yes / No / Not set" in body  # fixed flags render as BOOL_OR_NONE
        assert b"Email" in body  # email fixed row renders as EMAIL type

    def test_update_accepts_field_type(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{custom.id}/update",
            data={
                "label": custom.label,
                "group": custom.group.value,
                "field_type": FieldType.LONGTEXT.value,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes")
        assert field.field_type == FieldType.LONGTEXT

    def test_changing_to_choice_seeds_default_option(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )

        logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{custom.id}/update",
            data={
                "label": custom.label,
                "group": custom.group.value,
                "field_type": FieldType.CHOICE_RADIO.value,
            },
            follow_redirects=False,
        )

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes")
        assert field.field_type == FieldType.CHOICE_RADIO
        assert field.options is not None
        assert len(field.options) >= 1

    def test_remove_option_drops_from_choice_field(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )
        with FakeUnitOfWork(store=fake_store) as uow:
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
            data={"value": "a"},
            follow_redirects=False,
        )

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes")
        assert field.options is not None
        assert [o.value for o in field.options] == ["b"]

    def test_update_option_changes_value_and_help_text(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.update_field(
                uow,
                admin_user.id,
                existing_assembly.id,
                custom.id,
                field_type=FieldType.CHOICE_RADIO,
                options=[
                    ChoiceOption(value="old", help_text="original help"),
                    ChoiceOption(value="other"),
                ],
            )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{custom.id}/options/update",
            data={
                "old_value": "old",
                "value": "renamed",
                "help_text": "updated help",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes")
        assert field.options is not None
        assert [o.value for o in field.options] == ["renamed", "other"]
        assert field.options[0].help_text == "updated help"

    def test_update_option_renders_edit_form(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.update_field(
                uow,
                admin_user.id,
                existing_assembly.id,
                custom.id,
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="one", help_text="first option")],
            )

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        body = response.data
        # The option value and help_text should both appear as editable input values.
        assert b'value="one"' in body
        assert b'value="first option"' in body
        # The update action URL should be wired up.
        assert f"/respondent-schema/fields/{custom.id}/options/update".encode() in body

    def test_guess_button_shown_when_conditions_met(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        assert b"Guess field types from data" in response.data

    def test_guess_button_hidden_when_no_respondents(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.initialise_empty_schema(uow, admin_user.id, existing_assembly.id)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        assert b"Guess field types from data" not in response.data

    def test_guess_button_hidden_when_no_text_fields(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)
        # Flip every non-fixed row away from TEXT so there's nothing to guess.
        with FakeUnitOfWork(store=fake_store) as uow:
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

    def test_switch_choice_back_to_text_clears_options(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.update_field(
                uow,
                admin_user.id,
                existing_assembly.id,
                custom.id,
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="a"), ChoiceOption(value="b")],
            )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{custom.id}/update",
            data={
                "label": custom.label,
                "group": custom.group.value,
                "field_type": FieldType.TEXT.value,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes")
        assert field.field_type == FieldType.TEXT
        assert field.options is None

    def test_fixed_row_rejects_field_type_change(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)
        email_field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "email")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{email_field.id}/update",
            data={
                "label": email_field.label,
                "group": email_field.group.value,
                "field_type": FieldType.TEXT.value,
            },
            follow_redirects=False,
        )
        # Redirect back with a flash; type change is silently ignored because is_fixed.
        assert response.status_code == 302

        email_field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "email")
        # Still EMAIL — the attempt was refused.
        assert email_field.field_type == FieldType.EMAIL
