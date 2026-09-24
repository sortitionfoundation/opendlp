# ABOUTME: Component tests for the database replacement selection dialog and its POST route
# ABOUTME: Drives the real selection page and start_db_replacement over a FakeUnitOfWork

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from opendlp.adapters import database
from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import RespondentStatus, SelectionRunStatus, SelectionTaskType
from opendlp.service_layer import respondent_service, target_csv_import
from opendlp.service_layer.assembly_service import create_assembly, update_csv_config, update_selection_settings
from opendlp.service_layer.replacement_targets import build_replacement_plan
from tests.fakes import FakeUnitOfWork


@pytest.fixture(autouse=True)
def _mapped_domain_objects():
    """Settings/CSV-config writes call SQLAlchemy flag_modified, which needs mapped classes."""
    database.start_mappers()


@pytest.fixture
def assembly(fake_store, admin_user):
    """Ten to select; Gender Male/Female [4,6]; Age 18-30 [3,5], 31-50 [3,5], 51+ [2,4]; ten respondents."""
    with FakeUnitOfWork(store=fake_store) as uow:
        created = create_assembly(
            uow=uow,
            title="Replacement Assembly",
            created_by_user_id=admin_user.id,
            question="What should we select?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            number_to_select=10,
        )
        assembly_id = created.id

    with FakeUnitOfWork(store=fake_store) as uow:
        update_selection_settings(uow=uow, user_id=admin_user.id, assembly_id=assembly_id, check_same_address=False)
    with FakeUnitOfWork(store=fake_store) as uow:
        update_csv_config(uow=uow, user_id=admin_user.id, assembly_id=assembly_id, settings_confirmed=True)

    targets_csv = "feature,value,min,max\nGender,Male,4,6\nGender,Female,4,6\nAge,18-30,3,5\nAge,31-50,3,5\nAge,51+,2,4"
    with FakeUnitOfWork(store=fake_store) as uow:
        target_csv_import.import_targets_from_csv(uow, admin_user.id, assembly_id, targets_csv)

    respondents_csv = """external_id,Gender,Age
1,Male,18-30
2,Female,31-50
3,Male,51+
4,Female,18-30
5,Male,31-50
6,Female,51+
7,Male,18-30
8,Female,31-50
9,Male,51+
10,Female,18-30
"""
    with FakeUnitOfWork(store=fake_store) as uow:
        respondent_service.import_respondents_from_csv(uow, admin_user.id, assembly_id, respondents_csv)

    with FakeUnitOfWork(store=fake_store) as uow:
        return uow.assemblies.get(assembly_id).create_detached_copy()


def _set_statuses(fake_store, assembly_id, statuses: dict[str, RespondentStatus]) -> None:
    with FakeUnitOfWork(store=fake_store) as uow:
        for respondent in uow.respondents.get_by_assembly_id(assembly_id):
            if respondent.external_id in statuses:
                respondent.selection_status = statuses[respondent.external_id]
        uow.commit()


@pytest.fixture
def assembly_after_withdrawal(fake_store, assembly):
    """1 confirmed, 3/4/5 selected, 2 withdrawn: four places held, six to fill.

    Age 31-50 then still needs 2 but only respondent 8 is left in the pool.
    """
    _set_statuses(
        fake_store,
        assembly.id,
        {
            "1": RespondentStatus.CONFIRMED,
            "2": RespondentStatus.WITHDRAWN,
            "3": RespondentStatus.SELECTED,
            "4": RespondentStatus.SELECTED,
            "5": RespondentStatus.SELECTED,
        },
    )
    return assembly


def _plan_form(fake_store, admin_user, assembly_id, **overrides: str) -> dict[str, str]:
    """A form carrying the calculated numbers, with named (category, value, field) cells overridden."""
    with FakeUnitOfWork(store=fake_store) as uow:
        plan = build_replacement_plan(uow, admin_user.id, assembly_id)
    form = {"number_to_select": str(plan.default_number)}
    for category in plan.categories:
        for row in category.rows:
            form[row.min_field] = str(row.calculated.min)
            form[row.max_field] = str(row.calculated.max)
            for key, value in overrides.items():
                field, cat, val = key.split("__")
                if cat == category.name and val == row.value:
                    form[row.min_field if field == "min" else row.max_field] = value
    return form


class TestReplacementCard:
    def test_card_is_disabled_before_any_selection(self, logged_in_admin, assembly):
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection")
        assert response.status_code == 200
        assert b"Run the initial selection first" in response.data
        assert b"Coming Soon" not in response.data

    def test_card_is_enabled_once_people_are_selected(self, logged_in_admin, assembly_after_withdrawal):
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection")
        assert response.status_code == 200
        assert b"Review the places still to fill" in response.data
        assert b"replacement_modal=open" in response.data

    def test_card_waits_for_a_running_selection(self, logged_in_admin, assembly_after_withdrawal, fake_store):
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.selection_run_records.add(
                SelectionRunRecord(
                    assembly_id=assembly_after_withdrawal.id,
                    task_id=uuid.uuid4(),
                    task_type=SelectionTaskType.SELECT_REPLACEMENT_FROM_DB,
                    status=SelectionRunStatus.RUNNING,
                )
            )
            uow.commit()
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection")
        assert b"Wait for the running selection to finish" in response.data


class TestReplacementDialog:
    def test_dialog_shows_the_calculated_targets(self, logged_in_admin, assembly_after_withdrawal):
        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection?replacement_modal=open"
        )
        assert response.status_code == 200
        html = response.data.decode()
        assert "db-replacement-modal" in html
        assert "4 people are selected or confirmed" in html
        assert "6 places are to be filled" in html
        assert "between 4 and 8" in html
        assert 'name="number_to_select"' in html
        assert 'value="6"' in html
        assert "short by 1" in html
        assert "Run Replacement Selection" in html

    def test_short_category_is_open_and_fine_one_is_closed(self, logged_in_admin, assembly_after_withdrawal):
        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection?replacement_modal=open"
        )
        html = response.data.decode()
        gender_block, age_block = sorted(
            (html[i : html.index("</details>", i)] for i in _indexes(html, "<details")),
            key=lambda block: "Gender" not in block[:600],
        )
        assert "Gender" in gender_block and " open" not in gender_block[: gender_block.index(">")]
        assert "Age" in age_block and " open" in age_block[: age_block.index(">")]

    def test_dialog_says_when_every_place_is_filled(self, logged_in_admin, assembly, fake_store):
        _set_statuses(fake_store, assembly.id, {str(n): RespondentStatus.SELECTED for n in range(1, 11)})
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/selection?replacement_modal=open")
        html = response.data.decode()
        assert "Every place is filled" in html
        assert "Run Replacement Selection" not in html

    def test_dialog_warns_when_places_to_fill_are_outside_the_range(
        self, logged_in_admin, assembly_after_withdrawal, fake_store
    ):
        """Twenty to select leaves sixteen to fill, but the gender targets allow at most eight."""
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.assemblies.get(assembly_after_withdrawal.id).number_to_select = 20
            uow.commit()
        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection?replacement_modal=open"
        )
        html = response.data.decode()
        assert "Warning: 16 places are to be filled" in html
        assert 'value="8"' in html

    def test_dialog_requires_login(self, client, assembly_after_withdrawal):
        response = client.get(f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection?replacement_modal=open")
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]


def _indexes(text: str, needle: str) -> list[int]:
    found, start = [], 0
    while (i := text.find(needle, start)) != -1:
        found.append(i)
        start = i + 1
    return found


class TestStartReplacement:
    def test_valid_submission_starts_the_task(self, logged_in_admin, assembly_after_withdrawal, fake_store, admin_user):
        form = _plan_form(fake_store, admin_user, assembly_after_withdrawal.id, **{"min__Age__31-50": "1"})

        with patch("opendlp.service_layer.sortition.tasks.run_select_from_db.delay") as mock_delay:
            mock_delay.return_value = Mock(id="celery-id")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection/db/replacement/run", data=form
            )

        assert response.status_code == 302
        assert "current_selection=" in response.headers["Location"]
        task_id = uuid.UUID(response.headers["Location"].split("current_selection=")[1])
        with FakeUnitOfWork(store=fake_store) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
        assert record is not None
        assert record.task_type == SelectionTaskType.SELECT_REPLACEMENT_FROM_DB
        assert record.settings_used["replacement"] == {
            "number_to_select_overall": 10,
            "held_total": 4,
            "calculated_number": 6,
            "number_to_select_used": 6,
            "edited": True,
        }
        age = next(c for c in record.targets_used if c["name"] == "Age")
        middle = next(v for v in age["values"] if v["value"] == "31-50")
        assert (middle["min"], middle["calculated_min"], middle["held"], middle["overall_min"]) == (1, 2, 1, 3)
        assert mock_delay.call_args.kwargs["targets_snapshot"] == record.targets_used

    def test_pool_shortfall_is_shown_beside_the_cell(
        self, logged_in_admin, assembly_after_withdrawal, fake_store, admin_user
    ):
        """Submitting the calculated numbers as they are: Age 31-50 needs 2, the pool has 1."""
        form = _plan_form(fake_store, admin_user, assembly_after_withdrawal.id)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection/db/replacement/run", data=form
        )

        assert response.status_code == 200
        html = response.data.decode()
        assert "db-replacement-modal" in html
        assert "only 1 eligible people" in html
        assert 'aria-invalid="true"' in html

    def test_bad_cell_is_rejected_and_the_typed_values_are_kept(
        self, logged_in_admin, assembly_after_withdrawal, fake_store, admin_user
    ):
        form = _plan_form(fake_store, admin_user, assembly_after_withdrawal.id, min__Gender__Male="lots")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection/db/replacement/run", data=form
        )

        assert response.status_code == 200
        html = response.data.decode()
        assert "Enter whole numbers of zero or more" in html
        assert 'value="lots"' in html

    def test_cross_category_conflict_is_an_error_at_the_top(
        self, logged_in_admin, assembly_after_withdrawal, fake_store, admin_user
    ):
        """Gender still needs 4 but Age is edited to allow at most 3."""
        form = _plan_form(
            fake_store,
            admin_user,
            assembly_after_withdrawal.id,
            **{"max__Age__18-30": "1", "max__Age__31-50": "1", "max__Age__51+": "1", "min__Age__31-50": "1"},
        )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection/db/replacement/run", data=form
        )

        assert response.status_code == 200
        html = response.data.decode()
        assert "Inconsistent numbers" in html
        assert "Gender" in html and "Age" in html

    def test_requires_confirmed_settings(self, logged_in_admin, assembly_after_withdrawal, fake_store, admin_user):
        with FakeUnitOfWork(store=fake_store) as uow:
            update_csv_config(
                uow=uow, user_id=admin_user.id, assembly_id=assembly_after_withdrawal.id, settings_confirmed=False
            )
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection/db/replacement/run",
            data={"number_to_select": "6"},
        )
        assert response.status_code == 302
        assert "source=csv" in response.headers["Location"]

    def test_requires_login(self, client, assembly_after_withdrawal):
        response = client.post(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection/db/replacement/run",
            data={"number_to_select": "6"},
        )
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_requires_assembly_management(self, logged_in_user, assembly_after_withdrawal):
        response = logged_in_user.post(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection/db/replacement/run",
            data={"number_to_select": "6"},
        )
        assert response.status_code in (302, 403)
        assert b"db-replacement-modal" not in response.data
