# ABOUTME: Component tests for the database replacement selection dialog and its POST route
# ABOUTME: Drives the real selection page and start_db_replacement over a FakeUnitOfWork

import re
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from opendlp.adapters import database
from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.value_objects import AssemblyRole, RespondentStatus, SelectionRunStatus, SelectionTaskType
from opendlp.service_layer import respondent_service, target_csv_import
from opendlp.service_layer.assembly_service import create_assembly, update_csv_config, update_selection_settings
from opendlp.service_layer.replacement_targets import build_replacement_plan
from opendlp.service_layer.user_service import grant_user_assembly_role
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


@pytest.fixture
def assembly_with_feasible_gaps(fake_store, assembly):
    """1 confirmed, 2/3/5 selected: four places held, six to fill, and the six left in the pool fit the targets.

    Calculated: Male 1-3, Female 3-5; 18-30 2-4, 31-50 1-3, 51+ 1-3. Pool: 4, 6, 7, 8, 9, 10.
    """
    _set_statuses(
        fake_store,
        assembly.id,
        {
            "1": RespondentStatus.CONFIRMED,
            "2": RespondentStatus.SELECTED,
            "3": RespondentStatus.SELECTED,
            "5": RespondentStatus.SELECTED,
        },
    )
    return assembly


def _plan_form(fake_store, admin_user, assembly_id, **overrides: str) -> dict[str, str]:
    """A form carrying the calculated numbers, with named (category, value, field) cells overridden."""
    with FakeUnitOfWork(store=fake_store) as uow:
        plan = build_replacement_plan(uow, admin_user.id, assembly_id)
    form = {"number_to_select": str(plan.calculated_number)}
    for category in plan.categories:
        for row in category.rows:
            form[row.min_field] = str(row.calculated.min)
            form[row.max_field] = str(row.calculated.max)
            for key, value in overrides.items():
                field, cat, val = key.split("__")
                if cat == category.name and val == row.value:
                    form[row.min_field if field == "min" else row.max_field] = value
    return form


def _input_value(html: str, name: str) -> str:
    """The value the input with this name was rendered with."""
    tag = re.search(rf'<input[^>]*\bname="{re.escape(name)}"[^>]*>', html, re.DOTALL)
    assert tag is not None, f"no input named {name}"
    value = re.search(r'\bvalue="([^"]*)"', tag.group(0))
    return value.group(1) if value else ""


def _run_records(fake_store, assembly_id) -> list[SelectionRunRecord]:
    with FakeUnitOfWork(store=fake_store) as uow:
        records, _total = uow.selection_run_records.get_by_assembly_id_paginated(assembly_id, 1, 50)
    return list(records)


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
        assert _input_value(html, "number_to_select") == "6"
        assert "Needs at least 2 but only 1 eligible" in html
        assert "Run Replacement Selection" in html

    def test_number_to_select_is_hidden_until_changed(self, logged_in_admin, assembly_after_withdrawal):
        """The places to fill are bold with a change link, and the number field starts collapsed."""
        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection?replacement_modal=open"
        )
        html = response.data.decode()
        assert "<strong>6 places are to be filled</strong>" in html
        assert 'data-number-editing="false"' in html
        assert 'aria-controls="number_to_select-section"' in html
        assert 'id="number_to_select-section" x-show="numberEditing"' in html

    def test_number_to_select_starts_open_when_it_differs_from_the_default(
        self, logged_in_admin, assembly_with_feasible_gaps, fake_store, admin_user
    ):
        form = _plan_form(fake_store, admin_user, assembly_with_feasible_gaps.id)
        form["number_to_select"] = "5"
        form["action"] = "recheck"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_with_feasible_gaps.id}/selection/db/replacement/run", data=form
        )

        assert 'data-number-editing="true"' in response.data.decode()

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
        assert "16 places are to be filled, but the replacement targets only allow" in html
        assert 'value="16"' in html
        assert 'value="8"' not in html
        assert "fewer than the 16 to select" in html

    def test_dialog_keeps_the_places_to_fill_when_below_the_minimum(
        self, logged_in_admin, assembly_after_withdrawal, fake_store
    ):
        """Seven to select leaves three to fill, but the targets still need four: the number stays at three."""
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.assemblies.get(assembly_after_withdrawal.id).number_to_select = 7
            uow.commit()
        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection?replacement_modal=open"
        )
        html = response.data.decode()
        assert "3 places are to be filled, but the replacement targets only allow between 4 and" in html
        assert 'value="3"' in html
        assert "more than the 3 to select" in html

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
        assert "only 1 eligible person" in html
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
        assert "The smallest maximum is 3 for feature &#39;Age&#39;" in html
        assert "The largest minimum is 4 for feature &#39;Gender&#39;" in html
        assert "one target needs at least 4 replacements while another allows at most 3" in html

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

    def test_requires_assembly_management(self, logged_in_user, assembly_after_withdrawal, fake_store, admin_user):
        """A form that would start a run for a manager starts nothing for anyone else."""
        form = _plan_form(fake_store, admin_user, assembly_after_withdrawal.id, **{"min__Age__31-50": "1"})

        with patch("opendlp.service_layer.sortition.tasks.run_select_from_db.delay") as mock_delay:
            response = logged_in_user.post(
                f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection/db/replacement/run", data=form
            )

        assert response.status_code == 403
        mock_delay.assert_not_called()
        assert _run_records(fake_store, assembly_after_withdrawal.id) == []

    def test_refuses_while_another_selection_is_running(
        self, logged_in_admin, assembly_after_withdrawal, fake_store, admin_user
    ):
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.selection_run_records.add(
                SelectionRunRecord(
                    assembly_id=assembly_after_withdrawal.id,
                    task_id=uuid.uuid4(),
                    task_type=SelectionTaskType.SELECT_FROM_DB,
                    status=SelectionRunStatus.RUNNING,
                    log_messages=[],
                    user_id=admin_user.id,
                )
            )
            uow.commit()
        form = _plan_form(fake_store, admin_user, assembly_after_withdrawal.id, **{"min__Age__31-50": "1"})

        with patch("opendlp.service_layer.sortition.tasks.run_select_from_db.delay") as mock_delay:
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection/db/replacement/run",
                data=form,
                follow_redirects=True,
            )

        mock_delay.assert_not_called()
        assert len(_run_records(fake_store, assembly_after_withdrawal.id)) == 1
        assert "A selection is already running for this assembly" in response.data.decode()


class TestFeasibilityInDialog:
    def test_opening_the_dialog_runs_the_check_and_reports_success(self, logged_in_admin, assembly_with_feasible_gaps):
        """The calculated targets fit the pool, so the dialog says so and offers no suggestions."""
        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_with_feasible_gaps.id}/selection?replacement_modal=open"
        )
        html = response.data.decode()
        assert response.status_code == 200
        assert "These targets can be met from the pool." in html
        assert "feasibility-suggestions" not in html
        assert "Recheck feasibility" in html

    def test_opening_with_a_shortfall_shows_the_note_and_a_suggestion(
        self, logged_in_admin, assembly_after_withdrawal, fake_store
    ):
        """Nine to select leaves five to fill from the five in the pool; Age 31-50 needs 2 but has 1, so lower it."""
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.assemblies.get(assembly_after_withdrawal.id).number_to_select = 9
            uow.commit()
        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection?replacement_modal=open"
        )
        html = response.data.decode()
        assert "Needs at least 2 but only 1 eligible" in html
        assert "feasibility-suggestions" in html
        assert "Age: 31-50, minimum 2 to 1" in html
        assert "Suggested minimum: 1 (currently 2)" in html
        assert "feasibility-ok" not in html

    def test_recheck_notes_follow_the_amended_targets(
        self, logged_in_admin, assembly_after_withdrawal, fake_store, admin_user
    ):
        """Lowering the short 31-50 minimum to 1 and rechecking: no shortfall note, no category problem, feasible."""
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.assemblies.get(assembly_after_withdrawal.id).number_to_select = 9
            uow.commit()
        form = _plan_form(fake_store, admin_user, assembly_after_withdrawal.id, **{"min__Age__31-50": "1"})
        form["action"] = "recheck"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection/db/replacement/run", data=form
        )

        html = response.data.decode()
        assert response.status_code == 200
        assert "short by" not in html
        assert "a value cannot be filled from the pool" not in html
        assert "no spare people in the pool" in html
        assert "feasibility-ok" in html

    def test_opening_with_too_few_people_says_so(self, logged_in_admin, assembly_after_withdrawal):
        """Six to fill from five in the pool: no committee exists, so the dialog says the pool is too small."""
        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection?replacement_modal=open"
        )
        html = response.data.decode()
        assert "Needs at least 2 but only 1 eligible" in html
        assert "Only 5 eligible people are in the pool, fewer than the 6 to select" in html
        assert "feasibility-suggestions" not in html

    def test_shortfall_on_recheck_shows_the_cell_error_and_the_suggestion_together(
        self, logged_in_admin, assembly_with_feasible_gaps, fake_store, admin_user
    ):
        """Raising the 31-50 minimum to 2 with one in the pool: the cell error and the solver's suggestion sit together."""
        form = _plan_form(fake_store, admin_user, assembly_with_feasible_gaps.id, **{"min__Age__31-50": "2"})
        form["action"] = "recheck"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_with_feasible_gaps.id}/selection/db/replacement/run", data=form
        )

        html = response.data.decode()
        assert "only 1 eligible person" in html
        assert "Suggested minimum: 1 (currently 2)" in html
        assert "Age: 31-50, minimum 2 to 1" in html

    def test_row_suggestion_wrapper_has_no_display_class(
        self, logged_in_admin, assembly_with_feasible_gaps, fake_store, admin_user
    ):
        """The hidden attribute only works on an element without a display utility class, so the wrapper carries none."""
        form = _plan_form(fake_store, admin_user, assembly_with_feasible_gaps.id, **{"min__Age__31-50": "2"})
        form["action"] = "recheck"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_with_feasible_gaps.id}/selection/db/replacement/run", data=form
        )

        html = response.data.decode()
        row_start = html.index("Suggested minimum: 1 (currently 2)")
        wrapper = html[html.rindex("<span", 0, row_start) : row_start]
        assert "data-suggestion-for" in wrapper
        assert "class=" not in wrapper

    def test_recheck_shows_suggestions_at_the_top_and_beside_the_cell(
        self, logged_in_admin, assembly_with_feasible_gaps, fake_store, admin_user
    ):
        """Capping 18-30 at 1 leaves only four people outside it, so six cannot be chosen; the algorithm suggests raising it."""
        form = _plan_form(
            fake_store, admin_user, assembly_with_feasible_gaps.id, **{"min__Age__18-30": "1", "max__Age__18-30": "1"}
        )
        form["action"] = "recheck"

        with patch("opendlp.service_layer.sortition.tasks.run_select_from_db.delay") as mock_delay:
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly_with_feasible_gaps.id}/selection/db/replacement/run", data=form
            )

        assert response.status_code == 200
        mock_delay.assert_not_called()
        html = response.data.decode()
        assert "feasibility-suggestions" in html
        assert "Age: 18-30, maximum 1 to 3" in html
        assert "Suggested maximum: 3 (currently 1)" in html
        for name, typed in form.items():
            if name != "action":
                assert _input_value(html, name) == typed
        assert "feasibility-ok" not in html
        assert html.index("Replacement targets</h3>") < html.index("feasibility-suggestions") < html.index("<details")

    def test_recheck_keeps_the_edited_numbers_and_number_to_select(
        self, logged_in_admin, assembly_with_feasible_gaps, fake_store, admin_user
    ):
        """Rechecking uses what is in the form: five to select with the edited cells passes and is echoed back."""
        form = _plan_form(fake_store, admin_user, assembly_with_feasible_gaps.id, min__Gender__Female="2")
        form["number_to_select"] = "5"
        form["action"] = "recheck"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_with_feasible_gaps.id}/selection/db/replacement/run", data=form
        )

        html = response.data.decode()
        assert response.status_code == 200
        assert "These targets can be met from the pool." in html
        for name, typed in form.items():
            if name != "action":
                assert _input_value(html, name) == typed
        assert _input_value(html, "number_to_select") == "5"

    def test_recheck_with_a_bad_cell_shows_the_error_and_no_verdict(
        self, logged_in_admin, assembly_with_feasible_gaps, fake_store, admin_user
    ):
        form = _plan_form(fake_store, admin_user, assembly_with_feasible_gaps.id, min__Gender__Male="many")
        form["action"] = "recheck"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_with_feasible_gaps.id}/selection/db/replacement/run", data=form
        )

        html = response.data.decode()
        assert response.status_code == 200
        assert "Enter whole numbers of zero or more" in html
        assert "feasibility-ok" not in html
        assert "feasibility-suggestions" not in html

    def test_run_does_not_block_on_infeasible_targets(
        self, logged_in_admin, assembly_with_feasible_gaps, fake_store, admin_user
    ):
        """Running skips the solver check, so targets that cannot be met still start the task."""
        form = _plan_form(
            fake_store, admin_user, assembly_with_feasible_gaps.id, **{"min__Age__18-30": "1", "max__Age__18-30": "1"}
        )
        form["action"] = "run"

        with patch("opendlp.service_layer.sortition.tasks.run_select_from_db.delay") as mock_delay:
            mock_delay.return_value = Mock(id="celery-id")
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly_with_feasible_gaps.id}/selection/db/replacement/run", data=form
            )

        assert response.status_code == 302
        assert "current_selection=" in response.headers["Location"]
        mock_delay.assert_called_once()


class TestViewerWithoutManagement:
    """Someone who may view the assembly but not manage it still gets the selection page."""

    @pytest.fixture
    def logged_in_reader(self, logged_in_user, regular_user, admin_user, assembly_after_withdrawal, fake_store):
        with FakeUnitOfWork(store=fake_store) as uow:
            grant_user_assembly_role(
                uow=uow,
                user_id=regular_user.id,
                assembly_id=assembly_after_withdrawal.id,
                role=AssemblyRole.READ_ONLY,
                current_user=admin_user,
            )
        return logged_in_user

    def test_link_to_the_open_dialog_renders_the_page_with_it_closed(self, logged_in_reader, assembly_after_withdrawal):
        response = logged_in_reader.get(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection?replacement_modal=open"
        )

        assert response.status_code == 200
        html = response.data.decode()
        assert "Replacement Selection" in html
        assert "db-replacement-modal" not in html


class TestDialogNotes:
    """The notes the dialog puts beside a target or a value when something about it is unusual."""

    def test_value_holding_more_than_its_target_allows_is_noted(
        self, logged_in_admin, assembly_after_withdrawal, fake_store
    ):
        with FakeUnitOfWork(store=fake_store) as uow:
            for category in uow.target_categories.get_by_assembly_id(assembly_after_withdrawal.id):
                for value in category.values:
                    if value.value == "18-30":
                        value.min, value.max = 0, 0
            uow.commit()

        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection?replacement_modal=open"
        )

        assert response.status_code == 200
        assert "more places held than the target allows" in response.data.decode()

    def test_target_with_no_respondent_field_says_so(self, logged_in_admin, assembly_after_withdrawal, fake_store):
        with FakeUnitOfWork(store=fake_store) as uow:
            region = TargetCategory(assembly_id=assembly_after_withdrawal.id, name="Region")
            region.add_value(TargetValue(value="North", min=0, max=10))
            uow.target_categories.add(region)
            uow.commit()

        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_after_withdrawal.id}/selection?replacement_modal=open"
        )

        assert response.status_code == 200
        html = response.data.decode()
        assert "db-replacement-modal" in html
        assert "no matching respondent field, so nobody counts as currently selected" in html
