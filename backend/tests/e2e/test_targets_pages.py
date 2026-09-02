"""ABOUTME: End-to-end PostgreSQL happy-path smokes for the backoffice targets blueprint
ABOUTME: Behavioural coverage (HTMX fragments, validation, auth, permissions) lives in tests/component/"""

import io

import pytest

from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.respondents import Respondent
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.service_layer.target_csv_import import import_targets_from_csv
from opendlp.service_layer.target_service import (
    add_target_value,
    create_target_category,
    get_targets_for_assembly,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token

VALID_TARGETS_CSV = b"feature,value,min,max\nGender,Male,3,7\nGender,Female,3,7\n"

# Base URL prefix for backoffice targets
PREFIX = "/backoffice/assembly"


def _targets_url(assembly_id, suffix=""):
    return f"{PREFIX}/{assembly_id}/targets{suffix}"


def _csrf(client, assembly_id):
    return get_csrf_token(client, _targets_url(assembly_id))


def _add_respondents(postgres_session_factory, assembly_id, respondents_data):
    """Helper to add respondents with given attributes to an assembly."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        for ext_id, attributes in respondents_data:
            uow.respondents.add(Respondent(assembly_id=assembly_id, external_id=ext_id, attributes=attributes))
        uow.commit()


class TestViewTargetsPage:
    def test_get_targets_page_shows_existing_categories(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        csv_content = "feature,value,min,max\nGender,Male,3,7\nGender,Female,3,7\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_targets_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=existing_assembly.id,
                csv_content=csv_content,
            )

        response = logged_in_admin.get(_targets_url(existing_assembly.id))
        assert response.status_code == 200
        assert b"Gender" in response.data
        assert b"Male" in response.data
        assert b"Female" in response.data
        assert b"Number to select:" in response.data


class TestUploadTargetsCsv:
    def test_upload_valid_csv_creates_targets(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/upload"),
            data={
                "csv_file": (io.BytesIO(VALID_TARGETS_CSV), "targets.csv"),
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"/backoffice/assembly/{existing_assembly.id}/targets" in response.location

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("Successfully imported" in msg for msg in flash_messages)


class TestAddCategoriesFromColumns:
    @pytest.mark.db_semantics
    def test_creates_categories_from_selected_columns(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        """Selecting respondent columns creates target categories with auto-added values."""
        _add_respondents(
            postgres_session_factory,
            existing_assembly.id,
            [
                ("1", {"Gender": "Male", "Region": "North"}),
                ("2", {"Gender": "Female", "Region": "South"}),
                ("3", {"Gender": "Female", "Region": "East"}),
            ],
        )

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/categories/add-from-columns"),
            data={
                "columns": ["Gender", "Region"],
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Gender" in response.data
        assert b"Region" in response.data
        # Values should have been auto-added for low-cardinality columns
        assert b"Male" in response.data
        assert b"Female" in response.data
        assert b"North" in response.data


class TestCheckTargets:
    @pytest.mark.db_semantics
    def test_check_with_valid_data_shows_success(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        csv_content = "feature,value,min,max\nGender,Male,3,7\nGender,Female,3,7\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_targets_from_csv(
                uow=uow, user_id=admin_user.id, assembly_id=existing_assembly.id, csv_content=csv_content
            )

        _add_respondents(
            postgres_session_factory,
            existing_assembly.id,
            [(f"p{i}", {"Gender": "Male" if i % 2 == 0 else "Female"}) for i in range(20)],
        )

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = uow.assemblies.get(existing_assembly.id)
            assembly.number_to_select = 10
            assembly.csv = AssemblyCSV(assembly_id=assembly.id)
            assembly.selection_settings = SelectionSettings(assembly_id=assembly.id, check_same_address=False)
            uow.commit()

        response = logged_in_admin.get(
            _targets_url(existing_assembly.id, "/check"),
            data={"csrf_token": _csrf(logged_in_admin, existing_assembly.id)},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"All checks passed" in response.data


class TestSaveAll:
    def test_saves_every_submitted_field(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=50.0)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            value_id = get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0].values[0].value_id

        prefix = f"cat[{category.id}]"
        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/save-all"),
            data={
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
                f"{prefix}[name]": "Gender",
                f"{prefix}[comment]": "from the census",
                f"{prefix}[source_url]": "https://www.ons.gov.uk/dataset",
                f"{prefix}[values][{value_id}][value]": "Male",
                f"{prefix}[values][{value_id}][percentage]": "60",
                f"{prefix}[values][{value_id}][comment]": "boosted by 2",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            saved = get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0]
        assert saved.comment == "from the census"
        assert saved.source_url == "https://www.ons.gov.uk/dataset"
        assert saved.values[0].percentage_target == 60.0
        assert saved.values[0].comment == "boosted by 2"

    def test_deleting_a_value_and_adding_another_in_one_save(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.assemblies.get(existing_assembly.id).number_to_select = 20
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=50.0)
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Female", percentage=50.0)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            values = get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0].values
        male_id, female_id = values[0].value_id, values[1].value_id

        prefix = f"cat[{category.id}]"
        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/save-all"),
            data={
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
                f"{prefix}[name]": "Gender",
                f"{prefix}[values][{male_id}][value]": "Male",
                f"{prefix}[values][{male_id}][percentage]": "50",
                f"{prefix}[values][{female_id}][value]": "Female",
                f"{prefix}[values][{female_id}][deleted]": "true",
                f"{prefix}[values][new-1][value]": "Non-binary",
                f"{prefix}[values][new-1][percentage]": "10",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            saved = get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0]
        assert [v.value for v in saved.values] == ["Male", "Non-binary"]
        assert (saved.values[1].min, saved.values[1].max) == (2, 3)

    def test_deleting_a_whole_category(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=100.0)

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/save-all"),
            data={
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
                f"cat[{category.id}][name]": "Gender",
                f"cat[{category.id}][deleted]": "true",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert get_targets_for_assembly(uow, admin_user.id, existing_assembly.id) == []

    def test_re_linking_a_value_from_the_bulk_form(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.assemblies.get(existing_assembly.id).number_to_select = 20
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
            add_target_value(
                uow,
                admin_user.id,
                existing_assembly.id,
                category.id,
                "Male",
                min_count=17,
                max_count=18,
                percentage=50.0,
            )

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            value_id = get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0].values[0].value_id

        prefix = f"cat[{category.id}]"
        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/save-all"),
            data={
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
                f"{prefix}[name]": "Gender",
                f"{prefix}[values][{value_id}][value]": "Male",
                f"{prefix}[values][{value_id}][percentage]": "50",
                f"{prefix}[values][{value_id}][relink]": "true",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            value = get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0].values[0]
        assert value.minmax_manual is False
        assert (value.min, value.max) == (10, 11)

    def test_a_submitted_sort_order_reorders_the_categories(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            gender = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
            age = create_target_category(uow, admin_user.id, existing_assembly.id, "Age")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/save-all"),
            data={
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
                f"cat[{gender.id}][name]": "Gender",
                f"cat[{gender.id}][sort_order]": "20",
                f"cat[{age.id}][name]": "Age",
                f"cat[{age.id}][sort_order]": "10",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            names = [c.name for c in get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)]
        assert names == ["Age", "Gender"]

    def test_adding_a_category_the_user_typed_into_the_form(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.assemblies.get(existing_assembly.id).number_to_select = 20
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/save-all"),
            data={
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
                f"cat[{category.id}][name]": "Gender",
                f"cat[{category.id}][sort_order]": "10",
                "cat[new-1][name]": "Age",
                "cat[new-1][sort_order]": "20",
                "cat[new-1][values][new-1][value]": "16-29",
                "cat[new-1][values][new-1][percentage]": "50",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            saved = get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)
        assert [c.name for c in saved] == ["Gender", "Age"]
        assert [v.value for v in saved[1].values] == ["16-29"]
        assert (saved[1].values[0].min, saved[1].values[0].max) == (10, 11)

    def test_a_duplicate_category_name_is_a_flash_not_a_500(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        """The unique index on (assembly_id, name) would otherwise be an IntegrityError."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/save-all"),
            data={
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
                f"cat[{category.id}][name]": "Gender",
                "cat[new-1][name]": "gender",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"already exists" in response.data
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert len(get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)) == 1

    def test_a_category_with_no_name_is_a_flash_not_a_rename_to_nothing(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/save-all"),
            data={
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
                f"cat[{category.id}][name]": "   ",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0].name == "Gender"

    def test_a_rejected_save_writes_nothing_at_all(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        """The good half of a rejected save must not land either."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", 3, 7)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            value_id = get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0].values[0].value_id

        prefix = f"cat[{category.id}]"
        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/save-all"),
            data={
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
                f"{prefix}[name]": "Gender",
                f"{prefix}[comment]": "from the census",
                f"{prefix}[values][{value_id}][value]": "Male",
                f"{prefix}[values][{value_id}][min]": "9",
                f"{prefix}[values][{value_id}][max]": "2",
            },
        )

        assert response.status_code == 200
        assert b"Max must be at least the min" in response.data

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            saved = get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0]
        assert saved.comment == "", "the category comment was written despite the rejected save"
        assert (saved.values[0].min, saved.values[0].max) == (3, 7)

    def test_every_error_comes_back_at_once(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        """One round trip per mistake is what makes a bulk form miserable."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", 3, 7)
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Female", 3, 7)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            values = get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0].values
        male_id, female_id = values[0].value_id, values[1].value_id

        prefix = f"cat[{category.id}]"
        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/save-all"),
            data={
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
                f"{prefix}[name]": "Gender",
                f"{prefix}[source_url]": "javascript:alert(1)",
                f"{prefix}[values][{male_id}][value]": "Male",
                f"{prefix}[values][{male_id}][min]": "9",
                f"{prefix}[values][{male_id}][max]": "2",
                f"{prefix}[values][{female_id}][value]": "Female",
                f"{prefix}[values][{female_id}][min]": "8",
                f"{prefix}[values][{female_id}][max]": "1",
            },
        )

        html = response.data.decode()
        assert html.count("Max must be at least the min") == 2
        # The message the form shows, not the domain's own - that one is written
        # for a developer and never passes through gettext.
        assert "Enter a full http:// or https:// address" in html

    def test_saving_runs_the_detailed_check(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        """No separate "check targets" button: the save lands on the check itself."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=30.0)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            value_id = get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0].values[0].value_id

        prefix = f"cat[{category.id}]"
        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/save-all"),
            data={
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
                f"{prefix}[name]": "Gender",
                f"{prefix}[values][{value_id}][value]": "Male",
                f"{prefix}[values][{value_id}][percentage]": "30",
            },
        )

        assert response.status_code == 302
        assert response.location.endswith("/targets/check")

        landed = logged_in_admin.get(response.location)
        assert landed.status_code == 200
        assert b"Targets saved" in landed.data
        # The percentages come to 30, so the check's warning is on the page.
        assert b"add up to" in landed.data

    def test_an_invalid_source_url_is_a_flash_not_a_500(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/save-all"),
            data={
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
                f"cat[{category.id}][name]": "Gender",
                f"cat[{category.id}][source_url]": "javascript:alert(1)",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0].source_url == ""
