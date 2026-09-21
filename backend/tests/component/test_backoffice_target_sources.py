"""ABOUTME: Component tests for the target data sources checklist over a FakeUnitOfWork
ABOUTME: Drives the real target-sources routes + services against a seeded fake store (no PostgreSQL)"""

import io
import re
import uuid

import pytest

from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    DerivationType,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.service_layer import derivation_service
from opendlp.service_layer.assembly_service import create_assembly
from tests.fakes import FakeUnitOfWork

HTMX = {"HX-Request": "true"}


def _seed_category(fake_store, assembly, name, values):
    with FakeUnitOfWork(store=fake_store) as uow:
        category = TargetCategory(
            assembly_id=assembly.id,
            name=name,
            values=[TargetValue(value=value, min=1, max=5) for value in values],
        )
        uow.target_categories.add(category)
    return category


def _seed_field(fake_store, assembly, field_key, **kwargs):
    with FakeUnitOfWork(store=fake_store) as uow:
        field = RespondentFieldDefinition(
            assembly_id=assembly.id,
            field_key=field_key,
            label=kwargs.pop("label", field_key),
            group=kwargs.pop("group", RespondentFieldGroup.ABOUT_YOU),
            sort_order=kwargs.pop("sort_order", 10),
            **kwargs,
        )
        uow.respondent_field_definitions.add(field)
    return field


def _seed_respondents(fake_store, assembly, attributes_list):
    with FakeUnitOfWork(store=fake_store) as uow:
        for index, attributes in enumerate(attributes_list):
            uow.respondents.add(Respondent(assembly_id=assembly.id, external_id=f"R-{index}", attributes=attributes))


def _field_by_key(fake_store, assembly, field_key):
    with FakeUnitOfWork(store=fake_store) as uow:
        return uow.respondent_field_definitions.get_by_assembly_and_key(assembly.id, field_key)


class TestChecklistPage:
    def test_redirects_when_not_logged_in(self, client, existing_assembly):
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/target-sources", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.location

    def test_shows_empty_state_without_targets(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/target-sources")
        assert response.status_code == 200
        assert b"No targets have been set up" in response.data

    def test_shows_one_row_per_target_with_its_state(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])
        _seed_field(
            fake_store,
            existing_assembly,
            "Gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
            target_category_id=category.id,
        )
        _seed_category(fake_store, existing_assembly, "Region", ["North", "South"])

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/target-sources")

        assert response.status_code == 200
        assert b"Asked on the registration page" in response.data
        assert b"No data source yet" in response.data

    def test_status_marks_and_close_buttons_are_icons_not_text_glyphs(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        """A screen reader reads a bare tick or cross aloud, as "check mark" or "ballot x"."""
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])

        checklist = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/target-sources")
        modal = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/setup-modal", headers=HTMX
        )

        for body in (checklist.get_data(as_text=True), modal.get_data(as_text=True)):
            assert not re.search("[\u2713\u2717\u2715]", body)

    def test_flags_a_stale_linked_field(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female", "Other"])
        _seed_field(
            fake_store,
            existing_assembly,
            "Gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
            target_category_id=category.id,
        )

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/target-sources")

        assert b"The target's values have changed" in response.data

    def test_each_row_opens_its_set_up_dialog_from_anywhere_on_the_card(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        linked = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])
        _seed_field(
            fake_store,
            existing_assembly,
            "Gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
            target_category_id=linked.id,
        )
        unset = _seed_category(fake_store, existing_assembly, "Region", ["North", "South"])

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/target-sources")
        body = response.get_data(as_text=True)

        rows = re.findall(r'<li class="target-source-row[^"]*"[^>]*>(.*?)</li>', body, re.DOTALL)
        assert len(rows) == 2
        for row, category in zip(rows, (linked, unset), strict=True):
            # Exactly one link stretches over the card, and it opens that row's set-up dialog
            open_links = re.findall(r'<a href="([^"]*)"\s+role="button"\s+class="[^"]*\brow-link\b', row)
            assert open_links == [
                f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/setup-modal"
            ]

    def test_each_row_says_where_keyboard_focus_returns_when_its_dialog_closes(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        """fragment-dialog-focus.js finds the opener again by these, after the checklist has been re-rendered."""
        category = _seed_category(fake_store, existing_assembly, "Region", ["North", "South"])

        body = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/target-sources").get_data(as_text=True)

        assert 'id="ts-modal-container" data-fragment-dialog-host' in body
        assert f'data-focus-row="ts-{category.id}"' in body
        assert body.count(f'data-focus-id="ts-row-{category.id}"') == 1

    def test_the_dialog_backdrop_is_not_a_second_close_link_for_keyboard_users(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        """It is a pointer affordance: the X and Escape close the dialog from the keyboard."""
        category = _seed_category(fake_store, existing_assembly, "Region", ["North", "South"])

        body = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/setup-modal", headers=HTMX
        ).get_data(as_text=True)

        backdrop = re.search(r'<a [^>]*class="dialog-backdrop dialog-backdrop--clickable block"[^>]*>', body)
        assert backdrop is not None
        assert 'tabindex="-1"' in backdrop.group(0)
        assert 'aria-hidden="true"' in backdrop.group(0)
        assert "aria-label" not in backdrop.group(0)

    def test_opens_as_a_takeover_dialog_over_the_registration_hub(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/target-sources")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "dialog-panel--takeover" in body
        # The hub is painted behind the dialog, and made inert
        assert 'class="setup-step"' in body
        assert "No registration page created yet" in body
        assert re.search(r"<main [^>]*\binert\b", body)
        # Closing the dialog goes back to the hub
        assert f'href="/backoffice/assembly/{existing_assembly.id}/registration"' in body
        # Fragment dialogs open after the takeover, so Escape closes them first
        assert body.index("dialog-panel--takeover") < body.index('id="ts-modal-container"')

    def test_fragments_do_not_carry_the_hub(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])

        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/setup-modal", headers=HTMX
        )

        assert 'class="setup-step"' not in response.get_data(as_text=True)


def _flashes(client):
    with client.session_transaction() as session:
        return [message for _category, message in session.get("_flashes", [])]


# Every route on the blueprint, as (method, path after /target-sources).
_ALL_ROUTES = [
    ("get", ""),
    ("get", "/{category_id}/setup-modal"),
    ("post", "/{category_id}/configure"),
    ("post", "/{category_id}/adopt"),
    ("post", "/{category_id}/resync"),
    ("post", "/{category_id}/recompute"),
    ("get", "/{category_id}/upload-modal"),
    ("post", "/{category_id}/upload"),
    ("post", "/{category_id}/unlink"),
]


class TestRoutesTurnAwayThoseWithoutAccess:
    """No route may answer a refusal with a server error, whatever order it checks things in."""

    def _call(self, client, method, path, assembly_id, category_id):
        url = f"/backoffice/assembly/{assembly_id}/target-sources" + path.format(category_id=category_id)
        if method == "get":
            return client.get(url, follow_redirects=False)
        # A well-formed field_id, so the adopt route gets as far as asking the service.
        return client.post(url, data={"field_id": str(uuid.uuid4())}, follow_redirects=False)

    @pytest.mark.parametrize(("method", "path"), _ALL_ROUTES)
    def test_a_user_with_no_role_on_the_assembly_goes_back_to_the_dashboard(
        self, method, path, logged_in_user, existing_assembly, fake_store
    ):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])

        response = self._call(logged_in_user, method, path, existing_assembly.id, category.id)

        assert response.status_code == 302
        assert response.location.endswith("/backoffice/dashboard")
        (message,) = _flashes(logged_in_user)
        assert "permission" in message

    @pytest.mark.parametrize(("method", "path"), _ALL_ROUTES)
    def test_an_unknown_assembly_goes_back_to_the_dashboard(self, method, path, logged_in_admin):
        response = self._call(logged_in_admin, method, path, uuid.uuid4(), uuid.uuid4())

        assert response.status_code == 302
        assert response.location.endswith("/backoffice/dashboard")
        assert _flashes(logged_in_admin) == ["Assembly not found"]

    def test_an_invalid_set_up_form_from_a_user_with_no_role_is_still_turned_away(
        self, logged_in_user, existing_assembly, fake_store
    ):
        """The form is parsed before anyone checks who is asking, so the error path must check too."""
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])

        response = logged_in_user.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data={"method": ""},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location.endswith("/backoffice/dashboard")

    def test_a_target_of_another_assembly_cannot_be_set_up_from_this_one(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        with FakeUnitOfWork(store=fake_store) as uow:
            other = create_assembly(uow=uow, title="Another Assembly", created_by_user_id=admin_user.id)
            other_assembly = other.create_detached_copy()
        foreign = _seed_category(fake_store, other_assembly, "Gender", ["Male", "Female"])

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{foreign.id}/configure",
            data={"method": "exact", "source_mode": "create"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert _field_by_key(fake_store, existing_assembly, "Gender") is None
        assert _field_by_key(fake_store, other_assembly, "Gender") is None


class TestSetupModal:
    def _setup_url(self, assembly, category, query=""):
        return f"/backoffice/assembly/{assembly.id}/target-sources/{category.id}/setup-modal{query}"

    def test_starts_with_only_the_method_question(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])

        response = logged_in_admin.get(self._setup_url(existing_assembly, category), headers=HTMX)
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Set up data source for Gender" in body
        assert "How is the data collected?" in body
        assert re.search(r'<select\s+name="method"', body)
        assert re.search(r'<option value="" selected>\s*Choose one', body)
        for label in ("Exact copy", "Age ranges", "Map more options to fewer", "Map postcode to value"):
            assert label in body
        # Nothing else is asked until a method is chosen
        assert 'name="source_mode"' not in body
        assert "Target values:" not in body

    @pytest.mark.parametrize(("query", "expected"), [("", ""), ("?method=exact&dirty=1", "1")])
    def test_the_dialog_carries_its_unsaved_input_flag_through_a_refresh(
        self, query, expected, logged_in_admin, existing_assembly, fake_store
    ):
        """Opened fresh it is clean; a refresh after a choice comes back dirty, so closing still asks first."""
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])

        body = logged_in_admin.get(self._setup_url(existing_assembly, category, query), headers=HTMX).get_data(
            as_text=True
        )

        assert 'x-data="dialogLeaveGuard"' in body
        assert re.search(rf'name="dirty"\s+value="{expected}"\s+x-ref="dirtyInput"', body)
        assert len(re.findall(r'@click="guardLeave\(\$event\)"', body)) == 3
        assert "Discard changes?" in body

    def test_the_refresh_keeps_the_csrf_token_out_of_the_url(self, logged_in_admin, existing_assembly, fake_store):
        """The refresh is a GET that includes the whole form; a token in a URL reaches logs and history."""
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])

        body = logged_in_admin.get(self._setup_url(existing_assembly, category), headers=HTMX).get_data(as_text=True)

        refreshing = re.findall(r"<[^>]*hx-get=[^>]*hx-include=[^>]*>", body)
        assert refreshing
        assert all('hx-params="not csrf_token"' in tag for tag in refreshing)

    def test_editing_a_linked_target_opens_on_its_method(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])
        _seed_field(
            fake_store,
            existing_assembly,
            "Gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
            target_category_id=category.id,
        )

        response = logged_in_admin.get(self._setup_url(existing_assembly, category), headers=HTMX)
        body = response.get_data(as_text=True)

        assert "Edit data source for Gender" in body
        assert re.search(r'<option value="exact" selected>', body)
        assert "Ask the question with exactly the target&#39;s values as the answers" in body

    def test_with_nothing_to_reuse_it_names_the_question_it_will_create(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        category = _seed_category(fake_store, existing_assembly, "Age", ["16-29", "30-99"])

        response = logged_in_admin.get(
            self._setup_url(existing_assembly, category, "?modal=1&method=age_bracket&age_source_type=year"),
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert "A new question named 'year_of_birth' will be created" in body
        assert 'name="source_mode"' not in body
        assert 'name="new_field_key"' not in body
        assert "Create a new question" not in body

    def test_with_a_reusable_question_it_offers_the_choice(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])
        _seed_field(
            fake_store,
            existing_assembly,
            "sex",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
        )

        response = logged_in_admin.get(
            self._setup_url(existing_assembly, category, "?modal=1&method=exact"), headers=HTMX
        )
        body = response.get_data(as_text=True)

        assert "Use an existing question" in body
        assert "Create a new question" in body
        assert "will be created" not in body

    def test_saving_without_a_method_asks_for_one(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data={"modal": "1", "method": ""},
            headers=HTMX,
        )

        assert response.status_code == 422
        assert b"Choose how the data should be collected" in response.data

    def test_full_page_render_without_htmx(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])

        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/setup-modal"
        )

        assert response.status_code == 200
        assert b"target-sources-list" in response.data
        assert b"Exact copy" in response.data


class TestConfigureExactCopy:
    def test_create_makes_a_linked_choice_field(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data={"modal": "1", "method": "exact", "source_mode": "create"},
            headers=HTMX,
        )

        assert response.status_code == 200
        field = _field_by_key(fake_store, existing_assembly, "Gender")
        assert field is not None
        assert field.target_category_id == category.id
        assert [o.value for o in field.options] == ["Male", "Female"]
        # The response refreshes the checklist out-of-band, closing the modal.
        assert b"target-sources-list" in response.data
        assert b"hx-swap-oob" in response.data

    def test_reuse_links_the_chosen_field(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])
        field = _seed_field(
            fake_store,
            existing_assembly,
            "gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
        )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data={"modal": "1", "method": "exact", "source_mode": "reuse", "reuse_field_id": str(field.id)},
            headers=HTMX,
        )

        assert response.status_code == 200
        refreshed = _field_by_key(fake_store, existing_assembly, "gender")
        assert refreshed.target_category_id == category.id

    def test_conflicting_field_key_rerenders_the_modal_as_422(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])
        _seed_field(fake_store, existing_assembly, "Gender", field_type=FieldType.TEXT)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data={"modal": "1", "method": "exact", "source_mode": "create"},
            headers=HTMX,
        )

        assert response.status_code == 422
        assert b"already exists" in response.data
        # The error is an alert, so a screen reader announces it when the dialog is swapped in.
        assert re.search(r'role="alert".*?already exists', response.get_data(as_text=True), re.DOTALL)


class TestErrorsShownToTheOrganiser:
    """A not-found error names internal ids, so the page never shows its message."""

    def test_reusing_a_question_that_does_not_exist_shows_a_generic_message(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])
        missing = uuid.uuid4()

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data={"modal": "1", "method": "exact", "source_mode": "reuse", "reuse_field_id": str(missing)},
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 422
        assert re.search(r'role="alert".*?Question not found', body, re.DOTALL)
        assert str(missing) not in body
        assert str(existing_assembly.id) not in re.search(r'role="alert".*?</div>', body, re.DOTALL).group(0)

    def test_a_reuse_id_that_is_not_an_id_asks_for_a_question(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data={"modal": "1", "method": "exact", "source_mode": "reuse", "reuse_field_id": "not-an-id"},
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 422
        assert "Choose the question to use" in body
        assert "hexadecimal" not in body

    def test_adopting_a_question_that_does_not_exist_shows_a_generic_message(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])
        missing = uuid.uuid4()

        logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/adopt",
            data={"field_id": str(missing)},
        )

        assert _flashes(logged_in_admin) == ["Question not found"]

    def test_recomputing_a_target_with_nothing_linked_says_so(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])

        for action in ("resync", "recompute"):
            logged_in_admin.post(
                f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/{action}",
            )

        assert _flashes(logged_in_admin) == ["No question is linked to this target"] * 2


class TestConfigureAgeBrackets:
    def _age_form(self, **overrides):
        return {
            "modal": "1",
            "method": "age_bracket",
            "source_mode": "create",
            "new_field_key": "year_of_birth",
            "age_source_type": "year",
            "as_of_day": "1",
            "as_of_month": "6",
            "as_of_year": "2027",
            "min_age": "16",
            "max_age": "100",
            "boundaries": "30",
            **overrides,
        }

    def test_with_no_respondents_it_saves_without_a_recompute_report(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        category = _seed_category(fake_store, existing_assembly, "Age bracket", ["16-29", "30-99"])

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data=self._age_form(),
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "recomputed" not in body.lower()
        assert 'id="floating-alerts"' not in body
        # The checklist still refreshes out-of-band, closing the modal
        assert 'id="target-sources-list" hx-swap-oob="true"' in body
        derived = _field_by_key(fake_store, existing_assembly, "Age bracket")
        assert derived.is_derived is True
        assert derived.target_category_id == category.id
        assert _field_by_key(fake_store, existing_assembly, "year_of_birth") is not None

    def test_a_clean_recompute_is_reported_in_a_success_toast(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Age bracket", ["16-29", "30-99"])
        _seed_respondents(fake_store, existing_assembly, [{"year_of_birth": "1990"}, {"year_of_birth": "2005"}])

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data=self._age_form(),
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert re.search(r'id="floating-alerts"\s+hx-swap-oob="beforeend"', body)
        assert "Data source saved — Age bracket recomputed for every respondent" in body
        assert "var(--color-success-100)" in body
        assert "fell back" not in body
        # No report dialog: the toast replaces it
        assert "Respondents recomputed" not in body
        assert 'id="target-sources-list" hx-swap-oob="true"' in body

    def test_a_recompute_with_fallbacks_is_reported_in_a_warning_toast(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        category = _seed_category(fake_store, existing_assembly, "Age bracket", ["16-29", "30-99"])
        _seed_respondents(fake_store, existing_assembly, [{"year_of_birth": "1990"}, {"year_of_birth": "soon"}])

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data=self._age_form(),
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert "Data source saved — Age bracket recomputed for every respondent" in body
        assert "1 fell back to UNKNOWN" in body
        assert "var(--color-warning-100)" in body

    def test_without_htmx_the_toast_is_flashed_on_the_checklist(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Age bracket", ["16-29", "30-99"])
        _seed_respondents(fake_store, existing_assembly, [{"year_of_birth": "1990"}])

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data=self._age_form(),
            follow_redirects=True,
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Data source saved — Age bracket recomputed for every respondent" in body
        assert "Respondents recomputed" not in body

    def test_creates_the_named_source_when_no_name_is_given(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Age bracket", ["16-29", "30-99"])

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data={
                "modal": "1",
                "method": "age_bracket",
                "age_source_type": "year",
                "as_of_day": "1",
                "as_of_month": "6",
                "as_of_year": "2027",
                "min_age": "16",
                "max_age": "100",
                "boundaries": "30",
            },
            headers=HTMX,
        )

        assert response.status_code == 200
        source = _field_by_key(fake_store, existing_assembly, "year_of_birth")
        assert source is not None
        assert source.field_type == FieldType.INTEGER

    def test_invalid_date_rerenders_as_422(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Age bracket", ["16-29", "30-99"])

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data={
                "modal": "1",
                "method": "age_bracket",
                "source_mode": "create",
                "new_field_key": "date_of_birth",
                "as_of_day": "",
                "as_of_month": "",
                "as_of_year": "",
            },
            headers=HTMX,
        )

        assert response.status_code == 422
        assert b"as-of date" in response.data

    def test_a_rule_error_is_shown_in_the_organisers_words(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Age bracket", ["16-29", "30-99"])

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data=self._age_form(min_age="50", max_age="40", boundaries=""),
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 422
        assert "The maximum age must be greater than the minimum age" in body
        assert "max_age must be greater than min_age" not in body

    def test_brackets_prefill_from_the_target_and_the_date_from_the_assembly(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        """Choosing age ranges for a "16-24"-style target fills in min/max/boundaries and the as-of date."""
        category = _seed_category(fake_store, existing_assembly, "Age bracket", ["16-24", "25-39", "40-59", "60+"])

        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/setup-modal",
            query_string={"modal": "1", "method": "age_bracket", "source_mode": "create"},
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert re.search(r'name="min_age"[^>]*value="16"', body)
        assert re.search(r'name="max_age"[^>]*value="60"', body)
        assert re.search(r'name="boundaries"[^>]*value="25, 40"', body)
        assert re.search(rf'name="as_of_year"[^>]*value="{existing_assembly.first_assembly_date.year}"', body)


class TestConfigureLargeMapping:
    def test_creates_text_source_and_derived_field(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Region", ["North", "South"])

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data={"modal": "1", "method": "large_mapping", "source_mode": "create", "new_field_key": "Postcode"},
            headers=HTMX,
        )

        assert response.status_code == 200
        derived = _field_by_key(fake_store, existing_assembly, "Region")
        assert derived.derivation_type == DerivationType.LARGE_MAPPING
        assert derived.target_category_id == category.id
        assert _field_by_key(fake_store, existing_assembly, "Postcode").field_type == FieldType.TEXT

    def _configure(self, logged_in_admin, assembly, category, data, headers=HTMX, **kwargs):
        return logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/target-sources/{category.id}/configure",
            data={"modal": "1", "method": "large_mapping", **data},
            headers=headers,
            **kwargs,
        )

    def test_saving_moves_on_to_the_upload_step(self, logged_in_admin, existing_assembly, fake_store):
        """Save keeps the dialog open on step 2, and refreshes the row behind it."""
        category = _seed_category(fake_store, existing_assembly, "Region", ["North", "South"])

        response = self._configure(
            logged_in_admin, existing_assembly, category, {"source_mode": "create", "new_field_key": "Postcode"}
        )
        body = response.get_data(as_text=True)
        dialog, _sep, _checklist = body.partition('id="target-sources-list"')

        assert response.status_code == 200
        assert "Step 2 of 2" in dialog
        assert "Upload lookup table for Region" in dialog
        assert 'name="defer_upload"' in dialog
        assert 'name="setup_step"' in dialog
        assert "Upload later" in dialog
        assert "Cancel" not in dialog
        assert 'id="target-sources-list" hx-swap-oob="true"' in body
        assert 'id="floating-alerts"' not in body

    def test_the_upload_step_hides_the_step_one_recompute_report(self, logged_in_admin, existing_assembly, fake_store):
        """With an empty table every respondent falls back, so reporting it is noise."""
        category = _seed_category(fake_store, existing_assembly, "Region", ["North", "South"])
        _seed_respondents(fake_store, existing_assembly, [{"Postcode": "SW1A 1AA"}])

        response = self._configure(
            logged_in_admin, existing_assembly, category, {"source_mode": "create", "new_field_key": "Postcode"}
        )
        body = response.get_data(as_text=True)

        assert "Step 2 of 2" in body
        assert 'id="floating-alerts"' not in body
        assert "fell back" not in body

    def test_re_editing_with_an_empty_table_moves_on_to_the_upload_step(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        category, _field = TestMappingUpload()._linked_large_mapping(fake_store, existing_assembly)
        postcode = _field_by_key(fake_store, existing_assembly, "Postcode")

        response = self._configure(
            logged_in_admin,
            existing_assembly,
            category,
            {"source_mode": "reuse", "reuse_field_id": str(postcode.id)},
        )

        assert response.status_code == 200
        assert "Step 2 of 2" in response.get_data(as_text=True)

    def test_re_editing_with_a_table_uploaded_closes_the_dialog(self, logged_in_admin, existing_assembly, fake_store):
        category, _field = TestMappingUpload()._linked_large_mapping(fake_store, existing_assembly)
        TestMappingUpload()._upload(logged_in_admin, existing_assembly, category)
        postcode = _field_by_key(fake_store, existing_assembly, "Postcode")

        response = self._configure(
            logged_in_admin,
            existing_assembly,
            category,
            {"source_mode": "reuse", "reuse_field_id": str(postcode.id)},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Step 2 of 2" not in body
        assert 'id="target-sources-list" hx-swap-oob="true"' in body

    def test_without_htmx_saving_redirects_to_the_upload_step(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Region", ["North", "South"])

        response = self._configure(
            logged_in_admin,
            existing_assembly,
            category,
            {"source_mode": "create", "new_field_key": "Postcode"},
            headers={},
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith(f"/target-sources/{category.id}/upload-modal?step=setup")
        page = logged_in_admin.get(response.headers["Location"]).get_data(as_text=True)
        assert "Step 2 of 2" in page
        assert 'name="defer_upload"' in page

    def test_the_set_up_form_says_the_upload_comes_next(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Region", ["North", "South"])

        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/setup-modal",
            query_string={"modal": "1", "method": "large_mapping", "source_mode": "create"},
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert "After saving you'll upload the lookup table" in body
        assert "afterwards" not in body

    def test_editing_with_a_table_uploaded_says_saving_keeps_it(self, logged_in_admin, existing_assembly, fake_store):
        category, _field = TestMappingUpload()._linked_large_mapping(fake_store, existing_assembly)
        TestMappingUpload()._upload(logged_in_admin, existing_assembly, category)

        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/setup-modal",
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert "Saving keeps the existing lookup table of 1 rows" in body
        assert "After saving" not in body


class TestConfigureSmallMapping:
    def test_maps_an_existing_choice_field(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Age group", ["Younger", "Older"])
        source = _seed_field(
            fake_store,
            existing_assembly,
            "age_band",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="16-29"), ChoiceOption(value="30-99")],
        )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data={
                "modal": "1",
                "method": "small_mapping",
                "source_mode": "reuse",
                "reuse_field_id": str(source.id),
                "map_source": ["16-29", "30-99"],
                "map_target": ["Younger", "Older"],
            },
            headers=HTMX,
        )

        assert response.status_code == 200
        derived = _field_by_key(fake_store, existing_assembly, "Age group")
        assert derived.derivation_type == DerivationType.SMALL_MAPPING
        assert derived.derivation_config["mapping"] == {"16-29": "Younger", "30-99": "Older"}


class TestRowActions:
    def _linked_exact(self, fake_store, assembly, values_in_field=("Male", "Female")):
        category = _seed_category(fake_store, assembly, "Gender", ["Male", "Female"])
        field = _seed_field(
            fake_store,
            assembly,
            "Gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value=value) for value in values_in_field],
            target_category_id=category.id,
        )
        return category, field

    def test_adopt_links_the_matched_field(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])
        field = _seed_field(
            fake_store,
            existing_assembly,
            "gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
        )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/adopt",
            data={"field_id": str(field.id)},
            headers=HTMX,
        )

        assert response.status_code == 200
        assert _field_by_key(fake_store, existing_assembly, "gender").target_category_id == category.id

    def test_resync_regenerates_exact_options(self, logged_in_admin, existing_assembly, fake_store):
        category, _field = self._linked_exact(fake_store, existing_assembly)
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.target_categories.get(category.id)
            stored.add_value(TargetValue(value="Other", min=0, max=5))

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/resync",
            headers=HTMX,
        )

        assert response.status_code == 200
        refreshed = _field_by_key(fake_store, existing_assembly, "Gender")
        assert [o.value for o in refreshed.options] == ["Male", "Female", "Other"]

    def test_resync_of_a_derivation_that_no_longer_parses_says_to_set_it_up_again(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        """A stored config can predate a code change; the row must say so rather than fall over."""
        category = _seed_category(fake_store, existing_assembly, "Region", ["North", "South"])
        _seed_field(fake_store, existing_assembly, "area", field_type=FieldType.TEXT)
        _seed_field(
            fake_store,
            existing_assembly,
            "Region",
            group=RespondentFieldGroup.DERIVED,
            is_derived=True,
            derived_from=["area"],
            derivation_type=DerivationType.SMALL_MAPPING,
            derivation_config={"mapping": {}},
            field_type=FieldType.CHOICE_DROPDOWN,
            options=[ChoiceOption(value="North")],
            target_category_id=category.id,
        )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/resync",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location.endswith("/target-sources")
        assert _flashes(logged_in_admin) == ["This data source could not be re-synced — set it up again"]

    def test_unlink_clears_the_link_but_keeps_the_field(self, logged_in_admin, existing_assembly, fake_store):
        category, _field = self._linked_exact(fake_store, existing_assembly)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/unlink",
            headers=HTMX,
        )

        assert response.status_code == 200
        refreshed = _field_by_key(fake_store, existing_assembly, "Gender")
        assert refreshed is not None
        assert refreshed.target_category_id is None

    def _linked_age_bracket(self, fake_store, assembly):
        category = _seed_category(fake_store, assembly, "Age bracket", ["16-29", "30-99"])
        _seed_field(fake_store, assembly, "year_of_birth", field_type=FieldType.INTEGER)
        _seed_field(
            fake_store,
            assembly,
            "Age bracket",
            group=RespondentFieldGroup.DERIVED,
            is_derived=True,
            derived_from=["year_of_birth"],
            derivation_type=DerivationType.AGE_BRACKET,
            derivation_config={
                "as_of_date": "2027-06-01",
                "min_age": 16,
                "max_age": 100,
                "boundaries": [30],
                "fallback": "UNKNOWN",
            },
            field_type=FieldType.CHOICE_DROPDOWN,
            options=[ChoiceOption(value="16-29"), ChoiceOption(value="30-99"), ChoiceOption(value="UNKNOWN")],
            target_category_id=category.id,
        )
        return category

    def test_recompute_with_no_respondents_says_there_is_nothing_to_do(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        category = self._linked_age_bracket(fake_store, existing_assembly)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/recompute",
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "There are no respondents to recompute yet" in body
        assert "Respondents recomputed" not in body

    def test_recompute_reports_in_a_toast(self, logged_in_admin, existing_assembly, fake_store):
        category = self._linked_age_bracket(fake_store, existing_assembly)
        _seed_respondents(fake_store, existing_assembly, [{"year_of_birth": "1990"}, {"year_of_birth": "2001"}])

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/recompute",
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert "Recompute finished" in body
        assert re.search(r'id="floating-alerts"\s+hx-swap-oob="beforeend"', body)
        assert "Respondents recomputed" not in body

    def _row_actions(self, logged_in_admin, assembly):
        """Each row's (buttons outside the menu, items inside it), as text; items is None with no menu."""
        body = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/target-sources").get_data(as_text=True)
        rows = re.findall(r'<li class="target-source-row[^"]*"[^>]*>(.*?)</li>', body, re.DOTALL)
        actions = []
        for row in rows:
            visible, _sep, menu = row.partition('role="menu"')
            actions.append((
                re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", visible)),
                re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", menu)) if menu else None,
            ))
        return actions

    def test_unlink_sits_in_the_more_actions_menu(self, logged_in_admin, existing_assembly, fake_store):
        self._linked_exact(fake_store, existing_assembly)

        [(visible, menu)] = self._row_actions(logged_in_admin, existing_assembly)

        assert "Edit" in visible
        assert "Unlink" not in visible
        assert "Unlink" in menu
        assert "Recompute" not in menu
        assert "upload" not in menu.lower()

    def test_the_menu_is_wired_as_a_keyboard_menu_button(self, logged_in_admin, existing_assembly, fake_store):
        """role="menu" promises arrow keys; every item is out of the Tab order so the menu is one stop."""
        self._linked_exact(fake_store, existing_assembly)

        actions = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/target-sources").get_data(
            as_text=True
        )

        assert '@keydown="onToggleKeydown"' in actions
        assert '@keydown="onMenuKeydown"' in actions
        assert '@focusout="closeOnFocusOut"' in actions
        items = re.findall(r'<[^>]*role="menuitem"[^>]*>', actions)
        assert items
        assert all('tabindex="-1"' in item for item in items)

    def test_a_derived_row_puts_recompute_in_the_menu_too(self, logged_in_admin, existing_assembly, fake_store):
        self._linked_age_bracket(fake_store, existing_assembly)

        [(visible, menu)] = self._row_actions(logged_in_admin, existing_assembly)

        assert "Edit" in visible
        assert "Recompute" not in visible
        assert "Recompute" in menu
        # A computed question is removed rather than unlinked - nothing would list it afterwards
        assert "Delete computed question" in menu
        assert "Unlink" not in menu

    def test_the_first_lookup_table_upload_stays_out_of_the_menu(self, logged_in_admin, existing_assembly, fake_store):
        TestMappingUpload()._linked_large_mapping(fake_store, existing_assembly)

        [(visible, menu)] = self._row_actions(logged_in_admin, existing_assembly)

        assert "Upload table" in visible
        assert "upload" not in menu.lower()

    def test_replacing_an_uploaded_lookup_table_is_in_the_menu(self, logged_in_admin, existing_assembly, fake_store):
        category, _field = TestMappingUpload()._linked_large_mapping(fake_store, existing_assembly)
        logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/upload",
            data={"mapping_file": (io.BytesIO(b"Postcode,Region\nSW1A 1AA,North\n"), "mapping.csv")},
            content_type="multipart/form-data",
            headers=HTMX,
        )

        [(visible, menu)] = self._row_actions(logged_in_admin, existing_assembly)

        assert "Upload table" not in visible
        assert "Re-upload table" in menu

    def test_set_up_actions_are_never_in_a_menu(self, logged_in_admin, existing_assembly, fake_store):
        _seed_category(fake_store, existing_assembly, "Region", ["North", "South"])
        _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])
        _seed_field(
            fake_store,
            existing_assembly,
            "gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
        )
        actions = self._row_actions(logged_in_admin, existing_assembly)

        assert sorted(("Link it" in visible, "Set up" in visible) for visible, _menu in actions) == [
            (False, True),
            (True, True),
        ]
        assert all(menu is None for _visible, menu in actions)

    def test_unknown_category_404s_politely(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{uuid.uuid4()}/unlink",
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestMappingUpload:
    def _linked_large_mapping(self, fake_store, assembly):
        category = _seed_category(fake_store, assembly, "Region", ["North", "South"])
        _seed_field(fake_store, assembly, "Postcode", field_type=FieldType.TEXT, group=RespondentFieldGroup.ADDRESS)
        field = _seed_field(
            fake_store,
            assembly,
            "Region",
            group=RespondentFieldGroup.DERIVED,
            is_derived=True,
            derived_from=["Postcode"],
            derivation_type=DerivationType.LARGE_MAPPING,
            derivation_config={"fallback": "UNKNOWN"},
            field_type=FieldType.CHOICE_DROPDOWN,
            options=[ChoiceOption(value="North"), ChoiceOption(value="South"), ChoiceOption(value="UNKNOWN")],
            target_category_id=category.id,
        )
        return category, field

    def _upload(self, logged_in_admin, assembly, category, data=None):
        return logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/target-sources/{category.id}/upload",
            data={"mapping_file": (io.BytesIO(b"Postcode,Region\nSW1A 1AA,North\n"), "mapping.csv"), **(data or {})},
            content_type="multipart/form-data",
            headers=HTMX,
        )

    def _row_count(self, fake_store, field):
        with FakeUnitOfWork(store=fake_store) as uow:
            return uow.respondent_field_mapping_entries.count_for_field(field.id)

    def test_the_row_upload_dialog_is_not_a_set_up_step(self, logged_in_admin, existing_assembly, fake_store):
        category, _field = self._linked_large_mapping(fake_store, existing_assembly)

        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/upload-modal",
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert "Step 2 of 2" not in body
        assert 'name="defer_upload"' not in body
        assert "Upload later" not in body
        assert "Cancel" in body

    def test_the_set_up_step_can_be_opened_directly(self, logged_in_admin, existing_assembly, fake_store):
        category, _field = self._linked_large_mapping(fake_store, existing_assembly)

        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/upload-modal?step=setup",
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert "Step 2 of 2" in body
        assert "I don't have the lookup table yet" in body
        assert "fall back to UNKNOWN" in body

    def test_upload_later_with_the_box_ticked_closes_with_a_warning(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        category, field = self._linked_large_mapping(fake_store, existing_assembly)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/upload",
            data={"setup_step": "1", "defer_upload": "1", "form_action": "defer"},
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Data source saved. Until the lookup table is uploaded, everyone&#39;s Region will be UNKNOWN." in body
        assert "var(--color-warning-100)" in body
        assert 'id="target-sources-list" hx-swap-oob="true"' in body
        assert self._row_count(fake_store, field) == 0

    def test_upload_later_without_the_box_ticked_stays_on_the_step(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        category, field = self._linked_large_mapping(fake_store, existing_assembly)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/upload",
            data={"setup_step": "1", "form_action": "defer"},
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 422
        assert "Step 2 of 2" in body
        assert "Tick the box to upload the lookup table later" in body
        assert self._row_count(fake_store, field) == 0

    def test_a_missing_file_in_the_set_up_step_stays_on_the_step(self, logged_in_admin, existing_assembly, fake_store):
        category, _field = self._linked_large_mapping(fake_store, existing_assembly)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/upload",
            data={"setup_step": "1"},
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 422
        assert "Choose a CSV file" in body
        assert "Step 2 of 2" in body

    def test_a_bad_csv_in_the_set_up_step_stays_on_the_step(self, logged_in_admin, existing_assembly, fake_store):
        category, _field = self._linked_large_mapping(fake_store, existing_assembly)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/upload",
            data={"setup_step": "1", "mapping_file": (io.BytesIO(b"\xff\xfe\xfa"), "mapping.csv")},
            content_type="multipart/form-data",
            headers=HTMX,
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 422
        assert "could not be read as UTF-8" in body
        assert "Step 2 of 2" in body

    def test_uploading_in_the_set_up_step_shows_the_report(self, logged_in_admin, existing_assembly, fake_store):
        category, field = self._linked_large_mapping(fake_store, existing_assembly)

        response = self._upload(logged_in_admin, existing_assembly, category, {"setup_step": "1"})

        assert response.status_code == 200
        assert b"Rows stored:" in response.data
        assert self._row_count(fake_store, field) == 1

    def test_an_empty_table_is_flagged_on_its_row(self, logged_in_admin, existing_assembly, fake_store):
        self._linked_large_mapping(fake_store, existing_assembly)

        body = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/target-sources").get_data(as_text=True)

        assert "Until the lookup table is uploaded, everyone's Region is UNKNOWN." in body

    def _upload_csv(self, logged_in_admin, assembly, category, csv_content, allow_new_outputs=False):
        data = {"mapping_file": (io.BytesIO(csv_content.encode("utf-8")), "mapping.csv")}
        if allow_new_outputs:
            data["allow_new_outputs"] = "1"
        return logged_in_admin.post(
            f"/backoffice/assembly/{assembly.id}/target-sources/{category.id}/upload",
            data=data,
            content_type="multipart/form-data",
            headers=HTMX,
        )

    def test_upload_without_matching_headings_warns_that_the_first_row_was_not_stored(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        category, field = self._linked_large_mapping(fake_store, existing_assembly)

        response = self._upload_csv(logged_in_admin, existing_assembly, category, "SW1A 1AA,South\nM1 1AE,North\n")

        assert response.status_code == 200
        assert "The first row was used as column headings and not stored" in response.get_data(as_text=True)
        assert self._row_count(fake_store, field) == 1

    def test_upload_with_matching_headings_has_no_first_row_warning(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        category, _field = self._linked_large_mapping(fake_store, existing_assembly)

        response = self._upload_csv(logged_in_admin, existing_assembly, category, "Postcode,Region\nSW1A 1AA,South\n")

        assert response.status_code == 200
        assert "used as column headings" not in response.get_data(as_text=True)

    def test_empty_file_rerenders_as_422(self, logged_in_admin, existing_assembly, fake_store):
        category, _field = self._linked_large_mapping(fake_store, existing_assembly)

        response = self._upload_csv(logged_in_admin, existing_assembly, category, "")

        assert response.status_code == 422
        assert b"empty" in response.data

    def test_row_cap_is_enforced(self, logged_in_admin, existing_assembly, fake_store, monkeypatch):
        """The 500k cap, exercised with a lowered limit rather than a 500k-row file."""
        monkeypatch.setattr(derivation_service, "MAX_MAPPING_ROWS", 2)
        category, _field = self._linked_large_mapping(fake_store, existing_assembly)

        response = self._upload_csv(
            logged_in_admin, existing_assembly, category, "Postcode,Region\nA,North\nB,South\nC,North\n"
        )

        assert response.status_code == 422
        assert b"too many rows" in response.data

    def test_unknown_outputs_rejected_without_the_checkbox(self, logged_in_admin, existing_assembly, fake_store):
        category, _field = self._linked_large_mapping(fake_store, existing_assembly)

        response = self._upload_csv(logged_in_admin, existing_assembly, category, "Postcode,Region\nA,East\n")

        assert response.status_code == 422
        assert b"output values not in the field" in response.data

    def test_unknown_outputs_accepted_with_the_checkbox_and_extend_the_options(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        category, _field = self._linked_large_mapping(fake_store, existing_assembly)

        response = self._upload_csv(
            logged_in_admin, existing_assembly, category, "Postcode,Region\nA,East\n", allow_new_outputs=True
        )

        assert response.status_code == 200
        assert b"New output values added:" in response.data
        assert "East" in [o.value for o in _field_by_key(fake_store, existing_assembly, "Region").options]

    def test_upload_modal_names_the_field(self, logged_in_admin, existing_assembly, fake_store):
        category, _field = self._linked_large_mapping(fake_store, existing_assembly)

        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/upload-modal",
            headers=HTMX,
        )

        assert response.status_code == 200
        assert b"Upload lookup table for Region" in response.data

    def test_upload_stores_rows_and_shows_the_combined_report(self, logged_in_admin, existing_assembly, fake_store):
        category, field = self._linked_large_mapping(fake_store, existing_assembly)
        csv_bytes = io.BytesIO(b"Postcode,Region\nSW1A 1AA,North\nEH1 1AA,South\n")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/upload",
            data={"mapping_file": (csv_bytes, "mapping.csv")},
            content_type="multipart/form-data",
            headers=HTMX,
        )

        assert response.status_code == 200
        assert b"Rows stored:" in response.data
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.respondent_field_mapping_entries.count_for_field(field.id) == 2

    def test_the_report_names_the_rules_own_fallback_and_sample_size(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        category, field = self._linked_large_mapping(fake_store, existing_assembly)
        field.derivation_config = {"fallback": "Elsewhere"}
        field.options = [ChoiceOption(value="North"), ChoiceOption(value="South"), ChoiceOption(value="Elsewhere")]
        _seed_respondents(fake_store, existing_assembly, [{"Postcode": "ZZ9 9ZZ"}])

        body = self._upload(logged_in_admin, existing_assembly, category).get_data(as_text=True)

        assert "Fell back to Elsewhere:" in body
        assert "UNKNOWN" not in body
        assert f"(up to {derivation_service.UNMATCHED_SAMPLE_SIZE} shown)" in body

    @pytest.mark.parametrize(
        ("rows", "expected"),
        [(b"SW1A 1AA,North\n", "1 lookup row"), (b"SW1A 1AA,North\nEH1 1AA,South\n", "2 lookup rows")],
    )
    def test_the_row_counts_its_lookup_rows_in_the_right_number(
        self, rows, expected, logged_in_admin, existing_assembly, fake_store
    ):
        category, _field = self._linked_large_mapping(fake_store, existing_assembly)
        logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/upload",
            data={"mapping_file": (io.BytesIO(b"Postcode,Region\n" + rows), "mapping.csv")},
            content_type="multipart/form-data",
            headers=HTMX,
        )

        body = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/target-sources").get_data(as_text=True)

        assert re.search(rf"{expected}\b(?!s)", body)

    def test_missing_file_rerenders_as_422(self, logged_in_admin, existing_assembly, fake_store):
        category, _field = self._linked_large_mapping(fake_store, existing_assembly)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/upload",
            data={},
            headers=HTMX,
        )

        assert response.status_code == 422
        assert b"Choose a CSV file" in response.data
