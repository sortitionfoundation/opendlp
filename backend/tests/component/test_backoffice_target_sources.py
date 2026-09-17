"""ABOUTME: Component tests for the target data sources checklist over a FakeUnitOfWork
ABOUTME: Drives the real target-sources routes + services against a seeded fake store (no PostgreSQL)"""

import io
import re
import uuid

from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    DerivationType,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.targets import TargetCategory, TargetValue
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
        assert b"Asked on the registration form" in response.data
        assert b"No data source yet" in response.data

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


class TestSetupModal:
    def test_serves_the_method_chooser(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Gender", ["Male", "Female"])

        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/setup-modal",
            headers=HTMX,
        )

        assert response.status_code == 200
        assert b"Exact copy" in response.data
        assert b"Age ranges" in response.data
        assert b"Map from more options" in response.data
        assert b"Map postcode to value" in response.data

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


class TestConfigureAgeBrackets:
    def test_create_source_and_derived_field_shows_the_report(self, logged_in_admin, existing_assembly, fake_store):
        category = _seed_category(fake_store, existing_assembly, "Age bracket", ["16-29", "30-99"])

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/configure",
            data={
                "modal": "1",
                "method": "age_bracket",
                "source_mode": "create",
                "new_field_key": "date_of_birth",
                "age_source_type": "date",
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
        assert b"Respondents recomputed" in response.data
        derived = _field_by_key(fake_store, existing_assembly, "Age bracket")
        assert derived.is_derived is True
        assert derived.target_category_id == category.id
        assert _field_by_key(fake_store, existing_assembly, "date_of_birth") is not None

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

    def test_missing_file_rerenders_as_422(self, logged_in_admin, existing_assembly, fake_store):
        category, _field = self._linked_large_mapping(fake_store, existing_assembly)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/target-sources/{category.id}/upload",
            data={},
            headers=HTMX,
        )

        assert response.status_code == 422
        assert b"Choose a CSV file" in response.data
