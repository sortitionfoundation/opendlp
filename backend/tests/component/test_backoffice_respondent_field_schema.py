# ABOUTME: Component tests for the respondent field schema management UI over a FakeUnitOfWork
# ABOUTME: Drives the real backoffice schema routes + services against a seeded fake store (no PostgreSQL)

import io
import uuid

from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldGroup,
)
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.service_layer import derivation_service, respondent_field_schema_service
from opendlp.service_layer.respondent_field_spec_service import SPEC_VERSION
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
    def test_schema_page_renders_registration_state_as_chips(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """The row shows the registration state as a read-only chip, not an inline select."""
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Required" in body
        assert 'name="on_registration_page"' not in body

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
    def test_add_choice_field_without_options_is_rejected(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """The modal submits options wholesale, so a choice field with none is an error, not a seed."""
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/add",
            data={
                "field_key": "preferred_contact",
                "field_type": FieldType.CHOICE_RADIO.value,
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"at least one option" in response.data

        assert not any(
            f.field_key == "preferred_contact" for f in _get_schema(fake_store, admin_user, existing_assembly)
        )

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

    def test_add_button_links_to_the_modal_when_schema_exists(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        assert b"Add a field" in response.data
        assert f"/assembly/{existing_assembly.id}/respondent-schema/fields/new-modal".encode() in response.data

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
    def test_schema_page_renders_type_summary(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        body = response.data
        assert b"Summary" in body
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

    def test_changing_to_choice_without_options_is_rejected(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """The old seed-option_1 hack is gone: a choice type needs options in the same submission."""
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{custom.id}/update",
            data={
                "label": custom.label,
                "group": custom.group.value,
                "field_type": FieldType.CHOICE_RADIO.value,
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"options list" in response.data

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes")
        assert field.field_type == FieldType.TEXT

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

    def test_choice_options_render_as_a_summary_line(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """Options are listed read-only on the row; the inline option editor is gone."""
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
                options=[ChoiceOption(value="one", help_text="first option"), ChoiceOption(value="two")],
            )

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        body = response.data
        assert b"one, two" in body
        assert f"/respondent-schema/fields/{custom.id}/options/update".encode() not in body

    def test_long_option_lists_truncate_on_the_row(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """More than six options collapse to a count on the summary row."""
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
                field_type=FieldType.CHOICE_DROPDOWN,
                options=[ChoiceOption(value=f"opt_{i}") for i in range(9)],
            )

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "opt_5" in body
        assert "opt_6" not in body
        assert "and 3 more" in body

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


class TestFieldModal:
    """The HTMX add/edit field modal: fragments, full-page fallback, and saves."""

    def _base(self, existing_assembly):
        return f"/backoffice/assembly/{existing_assembly.id}/respondent-schema"

    def test_new_modal_htmx_returns_a_fragment(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """With HX-Request the route serves just the dialog, not a whole page."""
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/new-modal", headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "<html" not in body
        assert 'role="dialog"' in body
        assert "Add a field" in body

    def test_new_modal_plain_request_renders_the_page_with_the_modal_open(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Without JS, opening the modal is a full page load with the dialog rendered in."""
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(f"{self._base(existing_assembly)}/fields/new-modal")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "<html" in body
        assert 'role="dialog"' in body

    def test_edit_modal_prefills_the_field(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """The edit modal echoes label, help text, checked type radio and option rows."""
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
                help_text="pick one",
            )

        response = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/{custom.id}/edit-modal", headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'value="Custom notes"' in body
        assert "pick one" in body
        assert 'value="choice" checked' in body.replace("\n", " ") or ('value="choice"' in body and "checked" in body)
        assert 'value="one"' in body
        assert 'value="first option"' in body

    def test_add_via_modal_creates_field_with_options_and_help_text(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add",
            data={
                "modal": "1",
                "form_action": "save",
                "label": "Preferred contact",
                "field_key": "",
                "type_choice": "choice",
                "choice_style": "choice_dropdown",
                "option_value": ["Phone", "Email", ""],
                "option_help": ["Call me", "", ""],
                "help_text": "How should we reach you?",
                "on_registration_page": FieldOnRegistrationPage.YES_OPTIONAL.value,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        field = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "preferred_contact"
        )
        assert field.label == "Preferred contact"
        assert field.field_type == FieldType.CHOICE_DROPDOWN
        assert [(o.value, o.help_text) for o in field.options] == [("Phone", "Call me"), ("Email", "")]
        assert field.help_text == "How should we reach you?"
        assert field.on_registration_page == FieldOnRegistrationPage.YES_OPTIONAL

    def test_add_via_modal_generates_the_field_key_from_the_label(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add",
            data={
                "modal": "1",
                "form_action": "save",
                "label": "Favourite Colour!",
                "type_choice": "free_text",
                "free_text_subtype": "text",
                "help_text": "",
                "on_registration_page": FieldOnRegistrationPage.YES_REQUIRED.value,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert any(f.field_key == "favourite_colour" for f in _get_schema(fake_store, admin_user, existing_assembly))

    def test_add_via_modal_htmx_success_returns_oob_editor_fragment(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """A successful HTMX save swaps the editor out of band, which also closes the modal."""
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add",
            data={
                "modal": "1",
                "form_action": "save",
                "label": "Dietary needs",
                "type_choice": "free_text",
                "free_text_subtype": "text",
                "help_text": "",
                "on_registration_page": FieldOnRegistrationPage.YES_REQUIRED.value,
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'id="schema-editor"' in body
        assert "hx-swap-oob" in body
        assert "dietary_needs" in body

    def test_add_via_modal_duplicate_key_returns_422_modal_with_the_error(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add",
            data={
                "modal": "1",
                "form_action": "save",
                "label": "Custom notes",
                "type_choice": "free_text",
                "free_text_subtype": "text",
                "help_text": "",
                "on_registration_page": FieldOnRegistrationPage.YES_REQUIRED.value,
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 422
        body = response.get_data(as_text=True)
        assert "already exists" in body
        assert 'value="Custom notes"' in body

    def test_add_option_action_re_renders_the_form_with_an_extra_row(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """The options editor's add-another button round-trips without saving anything."""
        _seed_schema(fake_store, admin_user, existing_assembly)
        before = len(_get_schema(fake_store, admin_user, existing_assembly))

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add",
            data={
                "modal": "1",
                "form_action": "add_option",
                "label": "Preferred contact",
                "type_choice": "choice",
                "choice_style": "choice_radio",
                "option_value": ["Phone"],
                "option_help": ["Call me"],
                "help_text": "",
                "on_registration_page": FieldOnRegistrationPage.YES_REQUIRED.value,
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert body.count('name="option_value"') == 2
        assert 'value="Phone"' in body
        assert len(_get_schema(fake_store, admin_user, existing_assembly)) == before

    def test_remove_option_action_drops_the_row(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add",
            data={
                "modal": "1",
                "form_action": "remove_option_0",
                "label": "Preferred contact",
                "type_choice": "choice",
                "choice_style": "choice_radio",
                "option_value": ["Phone", "Email"],
                "option_help": ["", ""],
                "help_text": "",
                "on_registration_page": FieldOnRegistrationPage.YES_REQUIRED.value,
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'value="Phone"' not in body
        assert 'value="Email"' in body

    def test_edit_via_modal_updates_type_options_and_help_text(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/{custom.id}/update",
            data={
                "modal": "1",
                "form_action": "save",
                "label": "Notes",
                "type_choice": "choice",
                "choice_style": "choice_radio",
                "option_value": ["Yes", "No"],
                "option_help": ["", ""],
                "help_text": "a hint",
                "on_registration_page": FieldOnRegistrationPage.NO.value,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes")
        assert field.label == "Notes"
        assert field.field_type == FieldType.CHOICE_RADIO
        assert [o.value for o in field.options] == ["Yes", "No"]
        assert field.help_text == "a hint"
        assert field.on_registration_page == FieldOnRegistrationPage.NO

    def test_edit_via_modal_on_a_fixed_field_updates_label_and_help_only(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """A fixed field's modal has no type radios; saving changes label/help/registration state only."""
        _seed_schema(fake_store, admin_user, existing_assembly)
        email_field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "email")

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/{email_field.id}/update",
            data={
                "modal": "1",
                "form_action": "save",
                "label": "Email address",
                "help_text": "We only use this to contact you",
                "on_registration_page": FieldOnRegistrationPage.YES_REQUIRED.value,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "email")
        assert field.label == "Email address"
        assert field.help_text == "We only use this to contact you"
        assert field.field_type == FieldType.EMAIL  # stored type untouched

    def test_section_select_change_over_htmx_returns_the_editor_fragment(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """The row's section select posts just the group and gets the refreshed editor back."""
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/{custom.id}/update",
            data={"group": RespondentFieldGroup.ABOUT_YOU.value},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'id="schema-editor"' in body
        assert "hx-swap-oob" not in body

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes")
        assert field.group == RespondentFieldGroup.ABOUT_YOU

    def test_editing_a_legacy_typed_field_offers_its_type(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """LONGTEXT is excluded from the picker but shown, selected, when the field already has it."""
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.update_field(
                uow, admin_user.id, existing_assembly.id, custom.id, field_type=FieldType.LONGTEXT
            )

        edit = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/{custom.id}/edit-modal", headers={"HX-Request": "true"}
        )
        assert edit.status_code == 200
        assert 'value="longtext"' in edit.get_data(as_text=True)

        new = logged_in_admin.get(f"{self._base(existing_assembly)}/fields/new-modal", headers={"HX-Request": "true"})
        assert 'value="longtext"' not in new.get_data(as_text=True)

    def test_row_help_text_is_rendered_on_the_page(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.update_field(
                uow, admin_user.id, existing_assembly.id, custom.id, help_text="shown under the field"
            )

        response = logged_in_admin.get(self._base(existing_assembly))
        assert response.status_code == 200
        assert b"shown under the field" in response.data


class TestFieldSpecJson:
    """The hidden JSON endpoint a CSV generator reads before writing a file."""

    def test_redirects_when_not_logged_in(self, client, existing_assembly):
        response = client.get(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema.json",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "login" in response.location

    def test_user_without_access_gets_403_and_no_schema(self, logged_in_user, existing_assembly):
        response = logged_in_user.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema.json")
        assert response.status_code == 403
        body = response.get_json()
        assert "fields" not in body
        assert body["error"]

    def test_unknown_assembly_gets_404(self, logged_in_admin):
        response = logged_in_admin.get(f"/backoffice/assembly/{uuid.uuid4()}/respondent-schema.json")
        assert response.status_code == 404
        assert response.get_json()["error"]

    def test_returns_the_columns_of_the_imported_csv(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema.json")

        assert response.status_code == 200
        assert response.mimetype == "application/json"
        body = response.get_json()
        assert body["spec_version"] == SPEC_VERSION
        assert body["assembly"]["id"] == str(existing_assembly.id)
        assert body["csv"]["id_column"] == "external_id"
        # Every column of the seeded import round-trips into the spec.
        assert set(body["csv"]["columns"]) >= {
            "external_id",
            "first_name",
            "last_name",
            "gender",
            "postcode",
            "custom_notes",
        }
        assert body["csv"]["columns"][0] == "external_id"

    def test_reports_choice_options_and_target_values(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)
        gender = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.update_field(
                uow,
                admin_user.id,
                existing_assembly.id,
                gender.id,
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
            )
            uow.target_categories.add(
                TargetCategory(
                    assembly_id=existing_assembly.id,
                    name="gender",
                    values=[
                        TargetValue(value="Male", min=18, max=22),
                        TargetValue(value="Female", min=18, max=22),
                    ],
                )
            )

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema.json")

        assert response.status_code == 200
        body = response.get_json()
        gender_field = next(f for f in body["fields"] if f["field_key"] == "gender")
        assert gender_field["field_type"] == "choice_radio"
        assert [o["value"] for o in gender_field["options"]] == ["Male", "Female"]
        assert [v["value"] for v in gender_field["target_values"]] == ["Male", "Female"]
        assert gender_field["target_values"][0]["min"] == 18
        assert body["unmatched_target_categories"] == []


class TestDerivedFieldModal:
    """The derived-field flow: panel rendering, creation per method, editing, and reports."""

    def _base(self, existing_assembly):
        return f"/backoffice/assembly/{existing_assembly.id}/respondent-schema"

    def _seed_sources_and_targets(self, fake_store, admin_user, existing_assembly):
        """A year_of_birth INTEGER source, a gender choice source, and matching targets."""
        _seed_schema(fake_store, admin_user, existing_assembly)
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.add_field(
                uow,
                admin_user.id,
                existing_assembly.id,
                field_key="year_of_birth",
                field_type=FieldType.INTEGER,
            )
            gender = next(
                f
                for f in respondent_field_schema_service.get_schema(uow, admin_user.id, existing_assembly.id)
                if f.field_key == "gender"
            )
            respondent_field_schema_service.update_field(
                uow,
                admin_user.id,
                existing_assembly.id,
                gender.id,
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="Female"), ChoiceOption(value="Male")],
            )
            uow.target_categories.add(
                TargetCategory(
                    assembly_id=existing_assembly.id,
                    name="age bracket",
                    values=[
                        TargetValue(value="16-24", min=5, max=10),
                        TargetValue(value="25-39", min=5, max=10),
                        TargetValue(value="40-59", min=5, max=10),
                        TargetValue(value="60+", min=5, max=10),
                    ],
                )
            )
            uow.target_categories.add(
                TargetCategory(
                    assembly_id=existing_assembly.id,
                    name="gender group",
                    values=[
                        TargetValue(value="Women", min=10, max=12),
                        TargetValue(value="Men", min=10, max=12),
                    ],
                )
            )

    def _derived_form(self, **overrides):
        data = {
            "modal": "1",
            "form_action": "save",
            "type_choice": "derived",
            "target_name": "age bracket",
            "derivation_method": "age_bracket",
            "source_key": "year_of_birth",
            "as_of_day": "1",
            "as_of_month": "6",
            "as_of_year": "2026",
            "min_age": "16",
            "max_age": "60",
            "boundaries": "25, 40",
            "help_text": "",
            "label": "",
        }
        data.update(overrides)
        return data

    def test_derived_radio_is_disabled_without_targets(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/new-modal", headers={"HX-Request": "true"}
        )
        body = response.get_data(as_text=True)
        assert 'value="derived"' in body
        assert "Create targets first" in body

    def test_derived_panel_lists_targets_and_filters_sources_by_method(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Age brackets offer the INTEGER source but not the choice field; targets fill the select."""
        self._seed_sources_and_targets(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/new-modal",
            query_string={"modal": "1", "type_choice": "derived", "derivation_method": "age_bracket"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'value="age bracket"' in body
        assert 'value="gender group"' in body
        assert 'value="year_of_birth"' in body
        assert 'value="gender"' not in body  # a choice field can't feed an age bracket

    def test_age_config_prefills_boundaries_from_the_target_and_date_from_the_assembly(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Choosing a "16-24"-style target pre-fills min/max/boundaries; the as-of date comes from the assembly."""
        self._seed_sources_and_targets(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/new-modal",
            query_string={
                "modal": "1",
                "type_choice": "derived",
                "derivation_method": "age_bracket",
                "target_name": "age bracket",
            },
            headers={"HX-Request": "true"},
        )
        body = response.get_data(as_text=True)
        assert 'name="min_age"' in body
        assert 'value="16"' in body
        assert 'value="60"' in body
        assert 'value="25, 40"' in body
        # The as-of date inputs are pre-filled from first_assembly_date (set on the fixture).
        assert f'value="{existing_assembly.first_assembly_date.year}"' in body

    def test_create_age_bracket_derived_field_shows_the_recompute_report(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        self._seed_sources_and_targets(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add-derived",
            data=self._derived_form(),
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Derived field created" in body
        assert "Respondents recomputed" in body
        assert 'id="schema-editor"' in body
        assert "hx-swap-oob" in body

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "age bracket")
        assert field.is_derived
        assert field.derived_from == ["year_of_birth"]
        assert field.derivation_config["boundaries"] == [25, 40]
        assert [o.value for o in field.options] == ["under-16", "16-24", "25-39", "40-59", "60+", "UNKNOWN"]

    def test_create_small_mapping_derived_field(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        self._seed_sources_and_targets(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add-derived",
            data=self._derived_form(
                target_name="gender group",
                derivation_method="small_mapping",
                source_key="gender",
                map_source=["Female", "Male"],
                map_target=["Women", "Men"],
            ),
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "gender group")
        assert field.derivation_config["mapping"] == {"Female": "Women", "Male": "Men"}
        assert [o.value for o in field.options] == ["Women", "Men", "UNKNOWN"]

    def test_create_large_mapping_derived_field_with_an_empty_table(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        self._seed_sources_and_targets(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add-derived",
            data=self._derived_form(
                target_name="gender group",
                derivation_method="large_mapping",
                source_key="postcode",
            ),
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "gender group")
        assert field.derivation_config == {"fallback": "UNKNOWN"}
        assert [o.value for o in field.options] == ["Women", "Men", "UNKNOWN"]

    def test_invalid_age_config_returns_422_with_the_error_inline(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        self._seed_sources_and_targets(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add-derived",
            data=self._derived_form(as_of_month="13"),
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 422
        assert "as-of date" in response.get_data(as_text=True)

    def test_missing_target_returns_422(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        self._seed_sources_and_targets(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add-derived",
            data=self._derived_form(target_name=""),
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 422
        assert "Choose the target" in response.get_data(as_text=True)

    def _create_derived(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        self._seed_sources_and_targets(fake_store, admin_user, existing_assembly)
        logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add-derived",
            data=self._derived_form(),
            headers={"HX-Request": "true"},
        )
        return next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "age bracket")

    def test_edit_modal_for_a_derived_field_prefills_the_config(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        field = self._create_derived(logged_in_admin, existing_assembly, admin_user, fake_store)

        response = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/{field.id}/edit-modal", headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'value="25, 40"' in body
        assert "delete this field and create it again" in body
        assert 'name="on_registration_page"' not in body  # derived fields are never collected

    def test_update_derivation_config_recomputes_and_reports(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        field = self._create_derived(logged_in_admin, existing_assembly, admin_user, fake_store)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/{field.id}/derivation",
            data=self._derived_form(boundaries="30", label="Age bracket", help_text="derived from year of birth"),
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "Derivation updated" in response.get_data(as_text=True)

        stored = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "age bracket")
        assert stored.derivation_config["boundaries"] == [30]
        assert stored.help_text == "derived from year of birth"

    def test_derived_row_summarises_source_and_method(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        self._create_derived(logged_in_admin, existing_assembly, admin_user, fake_store)

        response = logged_in_admin.get(self._base(existing_assembly))
        body = response.get_data(as_text=True)
        assert "Derived from year_of_birth" in body
        assert "Age brackets" in body
        assert "Not on form" in body


class TestMappingUploadAndRecompute:
    """The lookup-table upload dialog and the per-row recompute action."""

    def _base(self, existing_assembly):
        return f"/backoffice/assembly/{existing_assembly.id}/respondent-schema"

    def _create_large_mapping_field(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """A postcode → region large-mapping derived field, created through the modal."""
        _seed_schema(fake_store, admin_user, existing_assembly)
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.target_categories.add(
                TargetCategory(
                    assembly_id=existing_assembly.id,
                    name="region",
                    values=[
                        TargetValue(value="North", min=5, max=10),
                        TargetValue(value="South", min=5, max=10),
                    ],
                )
            )
        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add-derived",
            data={
                "modal": "1",
                "form_action": "save",
                "type_choice": "derived",
                "target_name": "region",
                "derivation_method": "large_mapping",
                "source_key": "postcode",
                "help_text": "",
                "label": "",
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        return next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "region")

    def test_row_shows_the_zero_rows_nudge_and_the_upload_action(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        field = self._create_large_mapping_field(logged_in_admin, existing_assembly, admin_user, fake_store)

        response = logged_in_admin.get(self._base(existing_assembly))
        body = response.get_data(as_text=True)
        assert "0 rows — upload a lookup table" in body
        assert f"/fields/{field.id}/mapping-modal" in body
        assert f"/fields/{field.id}/recompute" in body

    def test_mapping_modal_renders_as_a_fragment(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        field = self._create_large_mapping_field(logged_in_admin, existing_assembly, admin_user, fake_store)

        response = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/{field.id}/mapping-modal", headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "<html" not in body
        assert 'name="mapping_file"' in body
        assert 'name="allow_new_outputs"' in body

    def test_mapping_modal_for_a_non_mapping_field_is_refused(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        plain = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "postcode")

        response = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/{plain.id}/mapping-modal", follow_redirects=True
        )
        assert response.status_code == 200
        assert b"Field not found." in response.data

    def _upload(self, logged_in_admin, existing_assembly, field, csv_content, allow_new_outputs=False):
        data = {"mapping_file": (io.BytesIO(csv_content.encode("utf-8")), "mapping.csv")}
        if allow_new_outputs:
            data["allow_new_outputs"] = "1"
        return logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/{field.id}/mapping-upload",
            data=data,
            content_type="multipart/form-data",
            headers={"HX-Request": "true"},
        )

    def test_upload_stores_the_table_and_shows_the_combined_report(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        field = self._create_large_mapping_field(logged_in_admin, existing_assembly, admin_user, fake_store)

        response = self._upload(
            logged_in_admin,
            existing_assembly,
            field,
            "postcode,region\nSW1A 1AA,South\nM1 1AE,North\n",
        )
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Lookup table uploaded" in body
        assert "Rows stored:" in body
        assert "Respondents recomputed" in body

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.respondent_field_mapping_entries.count_for_field(field.id) == 2

    def test_missing_file_returns_422(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        field = self._create_large_mapping_field(logged_in_admin, existing_assembly, admin_user, fake_store)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/{field.id}/mapping-upload",
            data={},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 422
        assert b"Choose a CSV file" in response.data

    def test_empty_file_returns_422(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        field = self._create_large_mapping_field(logged_in_admin, existing_assembly, admin_user, fake_store)

        response = self._upload(logged_in_admin, existing_assembly, field, "")
        assert response.status_code == 422
        assert b"empty" in response.data

    def test_row_cap_is_enforced(self, logged_in_admin, existing_assembly, admin_user, fake_store, monkeypatch):
        """The 500k cap, exercised with a lowered limit rather than a 500k-row file."""
        monkeypatch.setattr(derivation_service, "MAX_MAPPING_ROWS", 2)
        field = self._create_large_mapping_field(logged_in_admin, existing_assembly, admin_user, fake_store)

        response = self._upload(
            logged_in_admin,
            existing_assembly,
            field,
            "postcode,region\nA,North\nB,South\nC,North\n",
        )
        assert response.status_code == 422
        assert b"too many rows" in response.data

    def test_unknown_outputs_rejected_without_the_checkbox(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        field = self._create_large_mapping_field(logged_in_admin, existing_assembly, admin_user, fake_store)

        response = self._upload(logged_in_admin, existing_assembly, field, "postcode,region\nA,East\n")
        assert response.status_code == 422
        assert b"output values not in the field" in response.data

    def test_unknown_outputs_accepted_with_the_checkbox_and_extend_the_options(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        field = self._create_large_mapping_field(logged_in_admin, existing_assembly, admin_user, fake_store)

        response = self._upload(
            logged_in_admin, existing_assembly, field, "postcode,region\nA,East\n", allow_new_outputs=True
        )
        assert response.status_code == 200
        assert b"New output values added:" in response.data

        stored = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "region")
        assert "East" in [o.value for o in stored.options]

    def test_recompute_action_shows_the_report(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        field = self._create_large_mapping_field(logged_in_admin, existing_assembly, admin_user, fake_store)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/{field.id}/recompute",
            data={},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Recompute complete" in body
        assert "Respondents recomputed" in body
        assert 'id="schema-editor"' in body

    def test_recompute_on_a_non_derived_field_is_refused(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        plain = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "postcode")

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/{plain.id}/recompute",
            data={},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Field not found." in response.data
