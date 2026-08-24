"""ABOUTME: End-to-end PostgreSQL happy-path smokes for the backoffice targets blueprint
ABOUTME: Behavioural coverage (HTMX fragments, validation, auth, permissions) lives in tests/component/"""

import io

import pytest

from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.respondents import Respondent
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.service_layer.target_service import (
    add_target_value,
    create_target_category,
    get_targets_for_assembly,
    import_targets_from_csv,
    update_target_value,
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
        assert b"1 categories defined" in response.data


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


class TestAddCategory:
    def test_add_category_creates_and_redirects(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/categories"),
            data={
                "name": "Gender",
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Gender" in response.data


class TestDeleteCategory:
    def test_delete_category_redirects(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/delete"),
            data={"csrf_token": _csrf(logged_in_admin, existing_assembly.id)},
            follow_redirects=True,
        )
        assert response.status_code == 200


class TestAddValue:
    def test_add_value_to_category(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values"),
            data={
                "value": "Male",
                "min_count": "5",
                "max_count": "10",
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Male" in response.data


class TestEditValue:
    def test_edit_value(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2:
            cat = add_target_value(uow2, admin_user.id, existing_assembly.id, category.id, "Male", 5, 10)
        value_id = cat.values[0].value_id

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values/{value_id}"),
            data={
                "value": "Female",
                "min_count": "6",
                "max_count": "12",
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Female" in response.data


class TestDeleteValue:
    def test_delete_value(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2:
            cat = add_target_value(uow2, admin_user.id, existing_assembly.id, category.id, "Male", 5, 10)
        value_id = cat.values[0].value_id

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values/{value_id}/delete"),
            data={"csrf_token": _csrf(logged_in_admin, existing_assembly.id)},
            follow_redirects=True,
        )
        assert response.status_code == 200


class TestEditCategory:
    def test_rename_category(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}"),
            data={
                "name": "Sex",
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Sex" in response.data


class TestAddMissingValues:
    def test_add_missing_values_creates_values(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        """Adding missing respondent values bulk-creates them with min=0, max=0."""
        _add_respondents(
            postgres_session_factory,
            existing_assembly.id,
            [
                ("1", {"Gender": "Male"}),
                ("2", {"Gender": "Female"}),
                ("3", {"Gender": "Non-binary"}),
            ],
        )

        # Use a name that doesn't match a respondent column to avoid auto-populate
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Sex")
        # Add one value so the others are "missing"
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2:
            add_target_value(uow2, admin_user.id, existing_assembly.id, category.id, "Male", 3, 7)

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values/add-missing"),
            data={
                "missing_values": ["Female", "Non-binary"],
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Female" in response.data
        assert b"Non-binary" in response.data


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


class TestRespondentColumns:
    def test_respondent_columns_returns_fragment(self, logged_in_admin, existing_assembly, postgres_session_factory):
        """The respondent-columns HTMX partial renders the assembly's attribute columns."""
        _add_respondents(
            postgres_session_factory,
            existing_assembly.id,
            [
                ("1", {"Gender": "Male"}),
                ("2", {"Gender": "Female"}),
            ],
        )

        response = logged_in_admin.get(_targets_url(existing_assembly.id, "/respondent-columns"))

        assert response.status_code == 200
        assert b"Gender" in response.data


class TestMoveCategory:
    def test_move_down_then_up_restores_the_order(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            first = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
            second = create_target_category(uow, admin_user.id, existing_assembly.id, "Age")

        def order():
            with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
                return [c.name for c in get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)]

        assert order() == ["Gender", "Age"]

        logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{first.id}/move"),
            data={"direction": "down", "csrf_token": _csrf(logged_in_admin, existing_assembly.id)},
            follow_redirects=True,
        )
        assert order() == ["Age", "Gender"]

        logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{first.id}/move"),
            data={"direction": "up", "csrf_token": _csrf(logged_in_admin, existing_assembly.id)},
            follow_redirects=True,
        )
        assert order() == ["Gender", "Age"]
        assert second.id is not None

    def test_moving_the_first_category_up_is_a_no_op(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            first = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
            create_target_category(uow, admin_user.id, existing_assembly.id, "Age")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{first.id}/move"),
            data={"direction": "up", "csrf_token": _csrf(logged_in_admin, existing_assembly.id)},
            follow_redirects=True,
        )

        assert response.status_code == 200
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            names = [c.name for c in get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)]
        assert names == ["Gender", "Age"]

    def test_an_unknown_direction_is_rejected(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/move"),
            data={"direction": "sideways", "csrf_token": _csrf(logged_in_admin, existing_assembly.id)},
        )

        assert response.status_code == 400


class TestRelinkValue:
    def test_relink_restores_percentage_driven_minmax(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=50.0)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            reloaded = get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0]
            value_id = reloaded.values[0].value_id
            update_target_value(
                uow,
                admin_user.id,
                existing_assembly.id,
                category.id,
                value_id,
                value="Male",
                min_count=1,
                max_count=2,
            )

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values/{value_id}/relink"),
            data={"csrf_token": _csrf(logged_in_admin, existing_assembly.id)},
            follow_redirects=True,
        )

        assert response.status_code == 200
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            value = get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0].values[0]
        assert value.minmax_manual is False


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
