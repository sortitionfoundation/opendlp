# ABOUTME: Component tests for the respondent field schema management UI over a FakeUnitOfWork
# ABOUTME: Drives the real backoffice schema routes + services against a seeded fake store (no PostgreSQL)

import re
import uuid
from datetime import UTC, datetime

import pytest

from opendlp.domain.respondent_derivation import AgeBracket, AgeBracketRule, SmallMappingRule
from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    DerivationType,
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
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


def _input_value(body, input_id):
    """The value attribute of the rendered input carrying ``input_id``."""
    tag = re.search(rf'<input[^>]*id="{input_id}"[^>]*>', body)
    assert tag is not None, f"no input with id {input_id}"
    value = re.search(r'value="([^"]*)"', tag.group(0))
    return value.group(1) if value else ""


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


class TestBuiltInQuestions:
    """The code calls them fixed fields; the interface never says "fixed"."""

    def test_the_editor_does_not_tag_built_in_questions_as_fixed(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.initialise_empty_schema(uow, admin_user.id, existing_assembly.id)

        body = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema").get_data(
            as_text=True
        )

        assert "email" in body
        assert not re.search(r"\bfixed\b", re.sub(r"<[^>]+>", " ", body), re.IGNORECASE)

    def test_the_edit_modal_explains_the_type_without_saying_fixed(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.initialise_empty_schema(uow, admin_user.id, existing_assembly.id)
            email = uow.respondent_field_definitions.get_by_assembly_and_key(existing_assembly.id, "email")
            email_id = email.id

        body = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{email_id}/edit-modal",
            headers={"HX-Request": "true"},
        ).get_data(as_text=True)

        assert "This is a built-in question, so its type can't be changed." in body
        assert not re.search(r"\bfixed\b", re.sub(r"<[^>]+>", " ", body), re.IGNORECASE)


class TestQuestionsList:
    """A card per section and a row per question, each with its own Edit button."""

    def _page(self, logged_in_admin, assembly):
        return logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/respondent-schema").get_data(as_text=True)

    def _rows(self, body):
        return {
            re.search(r"<code[^>]*>([^<]+)</code>", row).group(1): row
            for row in re.findall(r'<tr class="question-row[^"]*">(.*?)</tr>', body, re.DOTALL)
        }

    def test_each_row_has_one_edit_link_and_the_row_itself_is_not_a_link(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        schema = _get_schema(fake_store, admin_user, existing_assembly)

        rows = self._rows(self._page(logged_in_admin, existing_assembly))

        assert rows
        for field_key, row in rows.items():
            field = next(f for f in schema if f.field_key == field_key)
            # Only the button opens the edit modal: nothing stretches a link over the row
            assert "row-link" not in row
            links = re.findall(r'<a href="([^"]*/edit-modal)"\s+role="button"', row)
            assert links == [
                f"/backoffice/assembly/{existing_assembly.id}/respondent-schema/fields/{field.id}/edit-modal"
            ]

    def test_each_rows_edit_button_is_labelled_with_an_icon(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        rows = self._rows(self._page(logged_in_admin, existing_assembly))

        assert rows
        for row in rows.values():
            edit = re.search(r'<a href="[^"]*/edit-modal"\s+role="button"[^>]*>(.*?)</a>', row, re.DOTALL)
            assert edit is not None
            assert re.fullmatch(
                r'<span class="btn-icon">\s*<svg.*</svg>\s*</span><span>Edit</span>', edit.group(1).strip(), re.DOTALL
            )

    def test_has_no_next_step_button_to_the_registration_pages(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """The page is a step dialog over the registration hub, so closing it already goes there."""
        _seed_schema(fake_store, admin_user, existing_assembly)

        body = self._page(logged_in_admin, existing_assembly)

        assert "Next: build your registration page" not in body

    def test_each_rows_question_is_its_row_header(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """A screen reader names the question when reading any other cell in its row."""
        _seed_schema(fake_store, admin_user, existing_assembly)

        rows = self._rows(self._page(logged_in_admin, existing_assembly))

        assert rows
        for field_key, row in rows.items():
            header = re.search(r'<th scope="row">(.*?)</th>', row, re.DOTALL)
            assert header is not None
            assert f">{field_key}</code>" in header.group(1)

    def test_every_section_has_its_own_add_button_even_when_empty(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        # Empty the Address section by moving its only question out
        postcode = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "postcode")
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.update_field(
                uow, admin_user.id, existing_assembly.id, postcode.id, group=RespondentFieldGroup.OTHER
            )
        assert not any(
            f.group == RespondentFieldGroup.ADDRESS for f in _get_schema(fake_store, admin_user, existing_assembly)
        )

        body = self._page(logged_in_admin, existing_assembly)

        for group in RespondentFieldGroup:
            add_link = f"/respondent-schema/fields/new-modal?group={group.value}"
            if group == RespondentFieldGroup.DERIVED:
                assert add_link not in body
            else:
                assert add_link in body
        assert "No questions in this section yet." in body

    def test_remove_is_in_the_row_menu_only_for_questions_that_can_be_removed(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        rows = self._rows(self._page(logged_in_admin, existing_assembly))

        assert ">Remove</button>" not in rows["email"]
        custom_notes = rows["custom_notes"]
        menu = custom_notes[custom_notes.index('role="menu"') :]
        assert 'class="menu-item menu-item--danger">Remove</button>' in menu
        assert "/fields/" in menu and "/delete" in menu
        # No separate bin button beside the edit link any more
        assert 'aria-label="Remove' not in custom_notes

    def test_a_built_in_question_alone_in_its_section_has_no_empty_menu(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.initialise_empty_schema(uow, admin_user.id, existing_assembly.id)
        schema = _get_schema(fake_store, admin_user, existing_assembly)
        email = next(f for f in schema if f.field_key == "email")
        assert [f.field_key for f in schema if f.group == email.group] == ["email"]

        rows = self._rows(self._page(logged_in_admin, existing_assembly))

        # Can't move, isn't derived, can't be removed: no kebab that opens onto nothing
        assert 'role="menu"' not in rows["email"]
        assert "More actions for" not in rows["email"]

    def test_a_removable_question_alone_in_its_section_still_has_its_menu(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        schema = _get_schema(fake_store, admin_user, existing_assembly)
        postcode = next(f for f in schema if f.field_key == "postcode")
        assert [f.field_key for f in schema if f.group == postcode.group] == ["postcode"]

        rows = self._rows(self._page(logged_in_admin, existing_assembly))

        assert "Move up" not in rows["postcode"]
        assert "Move down" not in rows["postcode"]
        assert ">Remove</button>" in rows["postcode"]

    def test_moves_are_in_the_row_menu_and_only_where_they_can_go(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        body = self._page(logged_in_admin, existing_assembly)
        rows = self._rows(body)

        # first_name and last_name share a section, in that order
        assert body.index('<code class="text-body-sm" style="color: var(--color-body-text);">first_name') < body.index(
            '<code class="text-body-sm" style="color: var(--color-body-text);">last_name'
        )
        first, last = rows["first_name"], rows["last_name"]
        assert 'role="menuitem" tabindex="-1" class="menu-item">Move down' in first
        assert last.count('role="menuitem" tabindex="-1" class="menu-item">Move up') == 1
        assert "Move up" not in rows["eligible"]
        # The old Section select and arrow columns are gone
        assert 'id="row-group-' not in body
        assert ">↑<" not in body


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
        assert b"Add a question" in response.data
        assert f"/assembly/{existing_assembly.id}/respondent-schema/fields/new-modal".encode() in response.data

    def test_add_form_absent_without_schema(self, logged_in_admin, existing_assembly):
        # No schema yet: the Initialise prompt shows instead of the add form.
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        assert b"Add a question" not in response.data


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
    def test_the_tab_bar_carries_no_fields_entry(self, logged_in_admin, existing_assembly):
        """The fields editor is reached through the Registration workflow, not its own tab."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=csv")
        assert response.status_code == 200
        assert f"/assembly/{existing_assembly.id}/respondent-schema".encode() not in response.data

    def test_the_old_route_still_serves_the_fields_editor(self, logged_in_admin, existing_assembly):
        # Bookmarks and in-flight links keep working; the page is step 2 now.
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        assert b"Registration questions" in response.data

    def test_opens_as_a_takeover_dialog_over_the_registration_hub(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "dialog-panel--takeover" in body
        assert 'class="setup-step"' in body
        assert re.search(r"<main [^>]*\binert\b", body)
        assert f'href="/backoffice/assembly/{existing_assembly.id}/registration"' in body
        assert body.index("dialog-panel--takeover") < body.index('id="field-modal-container"')


class TestFieldTypeAndOptions:
    def test_schema_page_renders_type_summary(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        body = response.data
        assert b"Question type" in body
        # Fixed flags are BOOL_OR_NONE; both bool types are a checkbox in question wording
        assert b"Checkbox" in body
        assert b"Yes / No" not in body
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
        assert b"A choice field needs at least one option" in response.data

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
        assert b"Guess question types from data" in response.data

    def test_guess_button_hidden_when_no_respondents(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.initialise_empty_schema(uow, admin_user.id, existing_assembly.id)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondent-schema")
        assert response.status_code == 200
        assert b"Guess question types from data" not in response.data

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
        assert b"Guess question types from data" not in response.data

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
        assert "Add a question" in body

    @pytest.mark.parametrize(("query", "expected"), [("", ""), ("?dirty=1", "1")])
    def test_the_modal_carries_its_unsaved_input_flag_through_a_refresh(
        self, query, expected, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Opened fresh it is clean; a refresh after typing comes back dirty, so closing still asks first."""
        _seed_schema(fake_store, admin_user, existing_assembly)

        body = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/new-modal{query}", headers={"HX-Request": "true"}
        ).get_data(as_text=True)

        assert 'x-data="dialogLeaveGuard"' in body
        assert re.search(rf'name="dirty"\s+value="{expected}"\s+x-ref="dirtyInput"', body)
        assert len(re.findall(r'@click="guardLeave\(\$event\)"', body)) == 3
        assert "Discard changes?" in body

    def test_the_modal_refresh_keeps_the_csrf_token_out_of_the_url(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """The refresh is a GET that includes the whole form; a token in a URL reaches logs and history."""
        _seed_schema(fake_store, admin_user, existing_assembly)

        body = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/new-modal", headers={"HX-Request": "true"}
        ).get_data(as_text=True)

        refreshing = re.findall(r"<[^>]*hx-get=[^>]*hx-include=[^>]*>", body)
        assert refreshing
        assert all('hx-params="not csrf_token"' in tag for tag in refreshing)

    def test_the_page_says_where_keyboard_focus_returns_when_a_dialog_closes(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """fragment-dialog-focus.js finds the opener again by these, after the editor has been re-rendered."""
        _seed_schema(fake_store, admin_user, existing_assembly)

        body = logged_in_admin.get(self._base(existing_assembly)).get_data(as_text=True)

        assert 'id="field-modal-container" data-fragment-dialog-host' in body
        edit_ids = re.findall(r'data-focus-id="(question-[^"]+)"', body)
        add_ids = re.findall(r'data-focus-id="(add-question-[^"]+)"', body)
        assert edit_ids and len(edit_ids) == len(set(edit_ids))
        assert add_ids and len(add_ids) == len(set(add_ids))

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
        assert re.search(r'<option value="choice_radio" selected>', body)
        assert 'value="one"' in body
        assert 'value="first option"' in body

    def _type_select(self, body):
        match = re.search(r'<select\s+name="question_type".*?</select>', body, re.DOTALL)
        assert match is not None, "no question type select"
        return match.group(0)

    def test_new_modal_asks_for_the_question_type_in_one_grouped_dropdown(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        body = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/new-modal", headers={"HX-Request": "true"}
        ).get_data(as_text=True)
        type_select = self._type_select(body)

        assert re.search(r'<option value="" selected>\s*Choose one', type_select)
        assert re.findall(r'<option value="([^"]*)"', type_select) == [
            "",
            "bool",
            "date",
            "text",
            "email",
            "integer",
            "choice_radio",
            "choice_dropdown",
        ]
        assert '<optgroup label="Text">' in type_select
        assert '<optgroup label="Choice">' in type_select
        # The old radios and follow-up selects are gone
        assert 'name="type_choice"' not in body
        assert 'name="free_text_subtype"' not in body
        assert 'name="choice_style"' not in body
        # Nothing type-specific until a type is chosen
        assert 'name="option_value"' not in body

    def test_choosing_a_choice_type_shows_its_advice_and_options(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        body = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/new-modal",
            query_string={"modal": "1", "question_type": "choice_dropdown", "label": "Region"},
            headers={"HX-Request": "true"},
        ).get_data(as_text=True)

        assert re.search(r'<option value="choice_dropdown" selected>', self._type_select(body))
        assert "Use for longer lists (typically more than 10 options)" in body
        assert 'name="option_value"' in body

    def test_saving_the_question_type_dropdown_sets_the_field_type(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add",
            data={
                "modal": "1",
                "form_action": "save",
                "label": "Favourite number",
                "question_type": "integer",
                "on_registration_page": FieldOnRegistrationPage.YES_OPTIONAL.value,
            },
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        field = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "favourite_number"
        )
        assert field.field_type == FieldType.INTEGER

    def test_saving_without_a_question_type_asks_for_one(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        before = len(_get_schema(fake_store, admin_user, existing_assembly))

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add",
            data={"modal": "1", "form_action": "save", "label": "Mystery", "question_type": ""},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 422
        assert b"Choose a question type" in response.data
        assert len(_get_schema(fake_store, admin_user, existing_assembly)) == before

    def test_edit_modal_keeps_a_legacy_type_on_offer(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.update_field(
                uow, admin_user.id, existing_assembly.id, custom.id, field_type=FieldType.LONGTEXT
            )

        body = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/{custom.id}/edit-modal", headers={"HX-Request": "true"}
        ).get_data(as_text=True)

        assert re.search(r'<option value="longtext" selected>', self._type_select(body))

    def test_the_nullable_bool_legacy_type_is_named_apart_from_the_plain_checkbox(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Both bool types are a checkbox, so the legacy one says what makes it different."""
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.update_field(
                uow, admin_user.id, existing_assembly.id, custom.id, field_type=FieldType.BOOL_OR_NONE
            )

        type_select = self._type_select(
            logged_in_admin.get(
                f"{self._base(existing_assembly)}/fields/{custom.id}/edit-modal", headers={"HX-Request": "true"}
            ).get_data(as_text=True)
        )

        assert re.search(r'<option value="bool" >\s*Checkbox\s*</option>', type_select)
        assert re.search(r'<option value="bool_or_none" selected>\s*Checkbox \(can be left unanswered\)', type_select)

    def _required_switch(self, body):
        match = re.search(r'<label class="switch-container">.*?</label>', body, re.DOTALL)
        assert match is not None, "no required switch"
        return match.group(0)

    def test_required_is_a_switch_with_no_not_on_form_choice(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        body = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/new-modal", headers={"HX-Request": "true"}
        ).get_data(as_text=True)

        switch = self._required_switch(body)
        assert re.search(r'role="switch"\s+name="required"', switch)
        assert 'name="required_switch" value="1"' in body
        assert 'name="on_registration_page"' not in body
        assert "Not on registration page" not in body

    def test_the_required_switch_says_what_each_type_of_question_needs(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        expected = {
            "": "Required",
            "bool": "Checkbox must be checked",
            "bool_or_none": "Checkbox must be checked",
            "text": "Text must be entered",
            "email": "Text must be entered",
            "integer": "Text must be entered",
            "choice_radio": "An option must be chosen",
            "choice_dropdown": "An option must be chosen",
            "date": "Full date must be entered",
        }

        for question_type, label in expected.items():
            body = logged_in_admin.get(
                f"{self._base(existing_assembly)}/fields/new-modal",
                query_string={"modal": "1", "question_type": question_type, "label": "Q"},
                headers={"HX-Request": "true"},
            ).get_data(as_text=True)
            assert f'<span class="switch-label">{label}</span>' in self._required_switch(body), question_type

    def test_the_required_switch_saves_required_or_optional(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )
        form = {
            "modal": "1",
            "form_action": "save",
            "label": "Custom notes",
            "question_type": "text",
            "help_text": "",
            "required_switch": "1",
        }

        for switch_on, expected in (
            (True, FieldOnRegistrationPage.YES_REQUIRED),
            (False, FieldOnRegistrationPage.YES_OPTIONAL),
        ):
            data = {**form, "required": "1"} if switch_on else form
            response = logged_in_admin.post(
                f"{self._base(existing_assembly)}/fields/{custom.id}/update", data=data, headers={"HX-Request": "true"}
            )
            assert response.status_code == 200
            saved = next(
                f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
            )
            assert saved.on_registration_page == expected

    def test_the_required_switch_shows_the_saved_state(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )

        for state, checked in (
            (FieldOnRegistrationPage.YES_REQUIRED, True),
            (FieldOnRegistrationPage.YES_OPTIONAL, False),
            (FieldOnRegistrationPage.NO, False),
        ):
            with FakeUnitOfWork(store=fake_store) as uow:
                respondent_field_schema_service.update_field(
                    uow, admin_user.id, existing_assembly.id, custom.id, on_registration_page=state
                )
            body = logged_in_admin.get(
                f"{self._base(existing_assembly)}/fields/{custom.id}/edit-modal", headers={"HX-Request": "true"}
            ).get_data(as_text=True)
            assert bool(re.search(r"\bchecked\b", self._required_switch(body))) is checked, state

    def _selected_group(self, body):
        select = re.search(r'<select[^>]*id="field-modal-group".*?</select>', body, re.DOTALL)
        assert select is not None, "no section select"
        selected = re.search(r'<option value="([^"]*)" selected>', select.group(0))
        return selected.group(1) if selected else ""

    def test_the_form_asks_for_the_question_not_a_label(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        body = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/new-modal", headers={"HX-Request": "true"}
        ).get_data(as_text=True)

        assert re.search(r'<label[^>]*for="field-modal-label"[^>]*>\s*Question\b', body)
        assert not re.search(r'<label[^>]*for="field-modal-label"[^>]*>\s*Label\b', body)

    def test_the_required_and_feeds_target_column_is_headed_notes(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        body = logged_in_admin.get(self._base(existing_assembly)).get_data(as_text=True)

        assert re.search(r'<th scope="col">\s*Notes\s*</th>', body)
        assert not re.search(r'<th scope="col">\s*Tags\s*</th>', body)

    def test_the_field_key_sits_behind_an_advanced_section_on_both_forms(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )

        new_body = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/new-modal", headers={"HX-Request": "true"}
        ).get_data(as_text=True)
        edit_body = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/{custom.id}/edit-modal", headers={"HX-Request": "true"}
        ).get_data(as_text=True)

        for body in (new_body, edit_body):
            details = re.search(
                r"<details[^>]*>\s*<summary[^>]*>\s*Advanced\s*</summary>.*?</details>", body, re.DOTALL
            )
            assert details is not None, "no Advanced section"
            assert "Field key" in details.group(0)
            assert "Change the field key" not in body
        assert 'id="field-modal-key"' in new_body
        assert "<code>custom_notes</code>" in edit_body

    def test_new_modal_defaults_to_the_other_section(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)

        body = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/new-modal", headers={"HX-Request": "true"}
        ).get_data(as_text=True)

        assert self._selected_group(body) == RespondentFieldGroup.OTHER.value
        assert f'<option value="{RespondentFieldGroup.DERIVED.value}"' not in body

    def test_new_modal_opened_from_a_section_chooses_that_section(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        body = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/new-modal",
            query_string={"group": RespondentFieldGroup.ADDRESS.value},
            headers={"HX-Request": "true"},
        ).get_data(as_text=True)

        assert self._selected_group(body) == RespondentFieldGroup.ADDRESS.value

    def test_add_via_modal_puts_the_question_in_the_chosen_section(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)

        logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add",
            data={
                "modal": "1",
                "form_action": "save",
                "label": "Flat number",
                "group": RespondentFieldGroup.ADDRESS.value,
                "type_choice": "free_text",
                "free_text_subtype": "text",
                "on_registration_page": FieldOnRegistrationPage.YES_OPTIONAL.value,
            },
            headers={"HX-Request": "true"},
        )

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "flat_number")
        assert field.group == RespondentFieldGroup.ADDRESS

    def test_edit_modal_shows_and_saves_the_section(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)
        custom = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes"
        )

        body = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/{custom.id}/edit-modal", headers={"HX-Request": "true"}
        ).get_data(as_text=True)
        assert self._selected_group(body) == custom.group.value
        assert custom.group != RespondentFieldGroup.ABOUT_YOU

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/{custom.id}/update",
            data={
                "modal": "1",
                "form_action": "save",
                "label": "Custom notes",
                "group": RespondentFieldGroup.ABOUT_YOU.value,
                "type_choice": "free_text",
                "free_text_subtype": "text",
                "help_text": "",
                "on_registration_page": FieldOnRegistrationPage.NO.value,
            },
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        moved = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes")
        assert moved.group == RespondentFieldGroup.ABOUT_YOU

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

    def test_add_via_modal_duplicate_option_values_return_422(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Two rows with the same value would derive and count as one, so the save is refused."""
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add",
            data={
                "modal": "1",
                "form_action": "save",
                "label": "Preferred contact",
                "type_choice": "choice",
                "choice_style": "choice_radio",
                "option_value": ["Phone", "Email", "Phone"],
                "option_help": ["", "", ""],
                "help_text": "",
                "on_registration_page": FieldOnRegistrationPage.YES_REQUIRED.value,
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 422
        body = response.get_data(as_text=True)
        assert "must be different" in body
        assert "appears more than once" in body

        assert not any(
            f.field_key == "preferred_contact" for f in _get_schema(fake_store, admin_user, existing_assembly)
        )

    def test_edit_via_modal_duplicate_option_values_return_422(
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
                "option_value": ["Yes", "Yes"],
                "option_help": ["", ""],
                "help_text": "",
                "on_registration_page": FieldOnRegistrationPage.NO.value,
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 422
        assert "appears more than once" in response.get_data(as_text=True)

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes")
        assert field.field_type == FieldType.TEXT  # nothing was saved

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

    def _mapped_choice_question(self, fake_store, admin_user, assembly):
        """A choice question, and a small mapping computed from it. Returns (question, derived)."""
        with FakeUnitOfWork(store=fake_store) as uow:
            question = RespondentFieldDefinition(
                assembly_id=assembly.id,
                field_key="ethnicity",
                label="Ethnicity",
                group=RespondentFieldGroup.ABOUT_YOU,
                sort_order=900,
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="White British"), ChoiceOption(value="White Irish")],
            )
            uow.respondent_field_definitions.add(question)
            derived, _report = derivation_service.create_derived_field(
                uow,
                admin_user.id,
                assembly.id,
                field_key="ethnicity_group",
                label="Ethnicity group",
                source_field_key="ethnicity",
                rule=SmallMappingRule(mapping={"White British": "White", "White Irish": "White"}),
            )
            return question.create_detached_copy(), derived

    def test_renaming_an_option_in_the_modal_carries_a_small_mapping_with_it(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """The dialog posts the whole option list; each row says what it was called when it opened."""
        _seed_schema(fake_store, admin_user, existing_assembly)
        question, derived = self._mapped_choice_question(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/{question.id}/update",
            data={
                "modal": "1",
                "form_action": "save",
                "label": "Ethnicity",
                "type_choice": "choice",
                "choice_style": "choice_radio",
                "option_original": ["White British", "White Irish"],
                "option_value": ["White (British)", "White Irish"],
                "option_help": ["", ""],
                "on_registration_page": FieldOnRegistrationPage.YES_REQUIRED.value,
            },
        )

        assert response.status_code == 302
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.respondent_field_definitions.get(derived.id)
            assert stored.derivation_config["mapping"] == {"White (British)": "White", "White Irish": "White"}

    def test_the_modal_remembers_what_each_option_was_called_through_a_round_trip(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Adding a row re-renders the form; a rename typed before that must still be known as one."""
        _seed_schema(fake_store, admin_user, existing_assembly)
        question, _derived = self._mapped_choice_question(fake_store, admin_user, existing_assembly)

        opened = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/{question.id}/edit-modal", headers={"HX-Request": "true"}
        ).get_data(as_text=True)
        assert re.findall(r'name="option_original" value="([^"]*)"', opened) == ["White British", "White Irish"]

        after_adding_a_row = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/{question.id}/update",
            data={
                "modal": "1",
                "form_action": "add_option",
                "label": "Ethnicity",
                "type_choice": "choice",
                "choice_style": "choice_radio",
                "option_original": ["White British", "White Irish"],
                "option_value": ["White (British)", "White Irish"],
                "option_help": ["", ""],
            },
            headers={"HX-Request": "true"},
        ).get_data(as_text=True)

        assert re.findall(r'name="option_original" value="([^"]*)"', after_adding_a_row) == [
            "White British",
            "White Irish",
            "",
        ]

    def test_edit_via_modal_strips_surrounding_space_from_the_help_text(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Create strips the help text, so an edit must too — otherwise a stray space sticks."""
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
                "type_choice": "free_text",
                "free_text_subtype": "text",
                "help_text": "  anything else?  ",
                "on_registration_page": FieldOnRegistrationPage.NO.value,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        field = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "custom_notes")
        assert field.help_text == "anything else?"

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


class TestDerivedFieldsLiveOnTargetSources:
    """Computed questions are set up on the target data sources step; this editor never shows or edits them."""

    def _base(self, existing_assembly):
        return f"/backoffice/assembly/{existing_assembly.id}/respondent-schema"

    def _create_derived(self, fake_store, admin_user, existing_assembly):
        """An age bracket computed from a year_of_birth question, created the way the target step does."""
        _seed_schema(fake_store, admin_user, existing_assembly)
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent_field_schema_service.add_field(
                uow,
                admin_user.id,
                existing_assembly.id,
                field_key="year_of_birth",
                field_type=FieldType.INTEGER,
            )
            derived, _report = derivation_service.create_derived_field(
                uow,
                admin_user.id,
                existing_assembly.id,
                field_key="age bracket",
                label="age bracket",
                source_field_key="year_of_birth",
                rule=AgeBracketRule(
                    as_of_date=datetime.now(UTC).date(),
                    brackets=(AgeBracket(16, "16-24"), AgeBracket(25, "25-39"), AgeBracket(40, "40+")),
                ),
            )
        return derived

    def test_derived_type_is_never_offered(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/new-modal", headers={"HX-Request": "true"}
        )
        body = response.get_data(as_text=True)
        assert 'value="derived"' not in body

    def test_a_question_type_the_modal_does_not_offer_is_refused(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """An unrecognised type must not quietly become a text question."""
        _seed_schema(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/add",
            data={
                "modal": "1",
                "form_action": "save",
                "label": "Age band",
                "type_choice": "derived",
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 422
        assert "Choose a question type" in response.get_data(as_text=True)
        assert not any(f.field_key == "age_band" for f in _get_schema(fake_store, admin_user, existing_assembly))

    def test_derived_fields_do_not_appear_on_the_fields_page(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        derived = self._create_derived(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(self._base(existing_assembly))
        body = response.get_data(as_text=True)
        assert "age bracket" not in body
        assert f"/fields/{derived.id}/" not in body

    def test_editing_a_derived_field_redirects_to_the_target_data_sources(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """An old link to a computed question's edit dialog lands where it is managed now."""
        derived = self._create_derived(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(f"{self._base(existing_assembly)}/fields/{derived.id}/edit-modal")
        assert response.status_code == 302
        assert response.location.endswith(f"/backoffice/assembly/{existing_assembly.id}/target-sources")

        page = logged_in_admin.get(response.location).get_data(as_text=True)
        assert "Computed questions are set up on the &#39;Link targets to questions&#39; step" in page

    def test_editing_a_derived_field_over_htmx_redirects_the_whole_page(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        derived = self._create_derived(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/{derived.id}/edit-modal", headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        assert response.headers["HX-Redirect"].endswith(f"/backoffice/assembly/{existing_assembly.id}/target-sources")

    def test_the_derived_field_routes_are_gone(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        derived = self._create_derived(fake_store, admin_user, existing_assembly)
        base = self._base(existing_assembly)

        assert logged_in_admin.post(f"{base}/fields/add-derived", data={}).status_code == 404
        assert logged_in_admin.post(f"{base}/fields/{derived.id}/derivation", data={}).status_code == 404
        assert logged_in_admin.get(f"{base}/fields/{derived.id}/mapping-modal").status_code == 404
        assert logged_in_admin.post(f"{base}/fields/{derived.id}/mapping-upload", data={}).status_code == 404
        assert logged_in_admin.post(f"{base}/fields/{derived.id}/recompute", data={}).status_code == 404

    def test_relabel_a_source_field_via_the_modal(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """A question something is computed from keeps its type, so relabelling it is fine."""
        self._create_derived(fake_store, admin_user, existing_assembly)
        source = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "year_of_birth"
        )

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/{source.id}/update",
            data={
                "modal": "1",
                "form_action": "save",
                "label": "Birth year",
                "type_choice": "free_text",
                "free_text_subtype": "integer",
                "help_text": "",
                "on_registration_page": FieldOnRegistrationPage.NO.value,
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "You can&#39;t change the type" not in response.get_data(as_text=True)

        stored = next(
            f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "year_of_birth"
        )
        assert stored.label == "Birth year"
        assert stored.field_type == FieldType.INTEGER


class TestTargetLinkedFieldUI:
    """A field that feeds a target renders a chip, and its edit modal locks type and answer values."""

    def _base(self, existing_assembly):
        return f"/backoffice/assembly/{existing_assembly.id}/respondent-schema"

    def _seed_linked_field(self, fake_store, admin_user, assembly):
        _seed_schema(fake_store, admin_user, assembly)
        with FakeUnitOfWork(store=fake_store) as uow:
            category = TargetCategory(
                assembly_id=assembly.id,
                name="Gender",
                values=[TargetValue(value="Male", min=1, max=5), TargetValue(value="Female", min=1, max=5)],
            )
            uow.target_categories.add(category)
            field = uow.respondent_field_definitions.get_by_assembly_and_key(assembly.id, "gender")
            field.update(
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
            )
            field.target_category_id = category.id
            return field.create_detached_copy()

    def test_editor_row_carries_the_feeds_target_chip(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        self._seed_linked_field(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(self._base(existing_assembly))
        body = response.get_data(as_text=True)
        assert "Feeds target: Gender" in body
        assert "/target-sources" in body

    def test_a_question_a_derived_target_is_computed_from_feeds_that_target(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        with FakeUnitOfWork(store=fake_store) as uow:
            region = TargetCategory(
                assembly_id=existing_assembly.id, name="Region", values=[TargetValue(value="North", min=1, max=5)]
            )
            ward = TargetCategory(
                assembly_id=existing_assembly.id, name="Ward", values=[TargetValue(value="Central", min=1, max=5)]
            )
            uow.target_categories.add(region)
            uow.target_categories.add(ward)
            for category in (region, ward):
                uow.respondent_field_definitions.add(
                    RespondentFieldDefinition(
                        assembly_id=existing_assembly.id,
                        field_key=category.name,
                        label=category.name,
                        group=RespondentFieldGroup.DERIVED,
                        sort_order=100,
                        is_derived=True,
                        derived_from=["postcode"],
                        derivation_type=DerivationType.LARGE_MAPPING,
                        derivation_config={"fallback": "UNKNOWN"},
                        field_type=FieldType.CHOICE_DROPDOWN,
                        options=[ChoiceOption(value=category.values[0].value), ChoiceOption(value="UNKNOWN")],
                        target_category_id=category.id,
                    )
                )

        body = logged_in_admin.get(self._base(existing_assembly)).get_data(as_text=True)

        # The postcode question itself carries no link, but both targets are computed from it
        postcode_row = re.search(
            r"<tr[^>]*>(?:(?!</tr>).)*<code[^>]*>postcode</code>(?:(?!</tr>).)*</tr>", body, re.DOTALL
        )
        assert postcode_row is not None
        assert "Feeds target: Region" in postcode_row.group(0)
        assert "Feeds target: Ward" in postcode_row.group(0)

    def test_edit_modal_locks_type_but_keeps_presentation_and_help_editable(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        field = self._seed_linked_field(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.get(
            f"{self._base(existing_assembly)}/fields/{field.id}/edit-modal", headers={"HX-Request": "true"}
        )
        body = response.get_data(as_text=True)
        assert "Feeds target: Gender" in body
        # The tag uses the backoffice's own tag style; GOV.UK's tag classes have no styles here.
        assert "govuk-tag" not in body
        assert re.search(r'<ul class="question-tags">.*?/target-sources.*?Feeds target: Gender', body, re.DOTALL)
        # The question type can only switch between the two choice styles; option help inputs remain.
        type_select = re.search(r'<select\s+name="question_type".*?</select>', body, re.DOTALL).group(0)
        assert re.findall(r'<option value="([^"]*)"', type_select) == ["choice_radio", "choice_dropdown"]
        assert 'name="option_help"' in body
        # Option values render as fixed text with hidden inputs, not editable boxes.
        assert 'name="option_value" value="Male"' in body

    def test_saving_help_text_and_presentation_succeeds(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        field = self._seed_linked_field(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/{field.id}/update",
            data={
                "modal": "1",
                "form_action": "save",
                "label": "Your gender",
                "type_choice": "choice",
                "choice_style": "choice_dropdown",
                "option_value": ["Male", "Female"],
                "option_help": ["", "Includes trans women"],
                "help_text": "",
                "on_registration_page": "yes_optional",
            },
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        stored = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "gender")
        assert stored.field_type == FieldType.CHOICE_DROPDOWN
        assert stored.label == "Your gender"
        assert stored.options[1].help_text == "Includes trans women"
        assert [o.value for o in stored.options] == ["Male", "Female"]

    def test_changing_answer_values_is_refused_with_an_explanation(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        field = self._seed_linked_field(fake_store, admin_user, existing_assembly)

        response = logged_in_admin.post(
            f"{self._base(existing_assembly)}/fields/{field.id}/update",
            data={
                "modal": "1",
                "form_action": "save",
                "label": "Gender",
                "type_choice": "choice",
                "choice_style": "choice_radio",
                "option_value": ["Male", "Non-binary"],
                "option_help": ["", ""],
                "help_text": "",
                "on_registration_page": "yes_required",
            },
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 422
        assert b"feeds a target" in response.data
        stored = next(f for f in _get_schema(fake_store, admin_user, existing_assembly) if f.field_key == "gender")
        assert [o.value for o in stored.options] == ["Male", "Female"]


# Every route on the blueprint that takes an assembly, as (method, path after /respondent-schema).
_ALL_SCHEMA_ROUTES = [
    ("get", ""),
    ("get", ".json"),
    ("post", "/initialise"),
    ("get", "/fields/new-modal"),
    ("get", "/fields/{field_id}/edit-modal"),
    ("post", "/fields/add"),
    ("post", "/fields/add-derived"),
    ("post", "/fields/{field_id}/derivation"),
    ("get", "/fields/{field_id}/mapping-modal"),
    ("post", "/fields/{field_id}/mapping-upload"),
    ("post", "/fields/{field_id}/recompute"),
    ("post", "/fields/{field_id}/update"),
    ("post", "/guess-types"),
    ("post", "/fields/{field_id}/options/add"),
    ("post", "/fields/{field_id}/options/update"),
    ("post", "/fields/{field_id}/options/remove"),
    ("post", "/fields/{field_id}/move"),
    ("post", "/fields/{field_id}/delete"),
]


class TestRoutesTurnAwayThoseWithoutAccess:
    """No route may answer a refusal with a server error, whatever order it checks things in.

    The modal routes are posted to as the modal posts, over HTMX: that is the
    path that re-renders the page around the modal when a save is refused.
    """

    def _call(self, client, method, path, assembly_id, field_id):
        url = f"/backoffice/assembly/{assembly_id}/respondent-schema" + path.format(field_id=field_id)
        if method == "get":
            return client.get(url, headers={"HX-Request": "true"})
        data = {"modal": "1", "field_key": "shoe_size", "type_choice": "text", "direction": "up", "value": "x"}
        return client.post(url, data=data, headers={"HX-Request": "true"})

    @pytest.mark.parametrize(("method", "path"), _ALL_SCHEMA_ROUTES)
    def test_a_user_with_no_role_on_the_assembly_is_turned_away(
        self, method, path, logged_in_user, existing_assembly, admin_user, fake_store
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        with FakeUnitOfWork(store=fake_store) as uow:
            field = uow.respondent_field_definitions.list_by_assembly(existing_assembly.id)[0]

        response = self._call(logged_in_user, method, path, existing_assembly.id, field.id)

        assert response.status_code in (302, 403, 404)
        assert b"shoe_size" not in response.data

    @pytest.mark.parametrize(("method", "path"), _ALL_SCHEMA_ROUTES)
    def test_an_unknown_assembly_is_turned_away(self, method, path, logged_in_admin):
        response = self._call(logged_in_admin, method, path, uuid.uuid4(), uuid.uuid4())

        assert response.status_code in (302, 404)


class TestOneUnitOfWorkPerRequest:
    """A page read in several transactions can disagree with itself; each request here opens one block.

    A save that fails is the exception: its block rolled back, so the dialog it
    re-opens is read in a second one. Every request also spends one block loading
    the signed-in user, which is counted and subtracted as the baseline.
    """

    @pytest.fixture
    def blocks_opened(self, monkeypatch):
        opened = []
        enter = FakeUnitOfWork.__enter__

        def counting_enter(uow):
            opened.append(uow)
            return enter(uow)

        monkeypatch.setattr(FakeUnitOfWork, "__enter__", counting_enter)
        return opened

    def _blocks_for(self, blocks_opened, send, baseline):
        blocks_opened.clear()
        response = send()
        return response, len(blocks_opened) - baseline

    def _baseline(self, blocks_opened, client):
        """The blocks a request costs before its route runs."""
        blocks_opened.clear()
        client.get("/backoffice/dev/does-not-exist")
        return len(blocks_opened)

    def _field_id(self, fake_store, assembly, field_key):
        with FakeUnitOfWork(store=fake_store) as uow:
            return uow.respondent_field_definitions.get_by_assembly_and_key(assembly.id, field_key).id

    def test_reads_and_saves_open_one_block_and_a_refused_save_two(
        self, logged_in_admin, existing_assembly, admin_user, fake_store, blocks_opened
    ):
        _seed_schema(fake_store, admin_user, existing_assembly)
        base = f"/backoffice/assembly/{existing_assembly.id}/respondent-schema"
        notes_id = self._field_id(fake_store, existing_assembly, "custom_notes")
        htmx = {"HX-Request": "true"}
        baseline = self._baseline(blocks_opened, logged_in_admin)
        new_question = {"modal": "1", "form_action": "save", "type_choice": "free_text", "free_text_subtype": "text"}

        requests = {
            "page": (lambda: logged_in_admin.get(base), 200, 1),
            "new dialog": (lambda: logged_in_admin.get(f"{base}/fields/new-modal", headers=htmx), 200, 1),
            "edit dialog": (lambda: logged_in_admin.get(f"{base}/fields/{notes_id}/edit-modal", headers=htmx), 200, 1),
            "add": (
                lambda: logged_in_admin.post(
                    f"{base}/fields/add", data={**new_question, "label": "Shoe size"}, headers=htmx
                ),
                200,
                1,
            ),
            "add refused": (
                lambda: logged_in_admin.post(
                    f"{base}/fields/add", data={**new_question, "label": "Shoe size"}, headers=htmx
                ),
                422,
                2,
            ),
            "update": (
                lambda: logged_in_admin.post(
                    f"{base}/fields/{notes_id}/update",
                    data={**new_question, "label": "Notes", "group": "other"},
                    headers=htmx,
                ),
                200,
                1,
            ),
        }
        for name, (send, status, blocks) in requests.items():
            response, opened = self._blocks_for(blocks_opened, send, baseline)
            assert (name, response.status_code, opened) == (name, status, blocks)
