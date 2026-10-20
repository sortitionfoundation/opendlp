# ABOUTME: Component tests for accepting the algorithm's recommended target changes (sc-281)
# ABOUTME: Covers the accept-suggestions route (one/all, comment, re-run gating) and the failure-view link

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from opendlp.adapters import database
from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.service_layer.assembly_service import create_assembly, update_csv_config
from opendlp.service_layer.target_checking import DetailedCheckResult, TargetAnnotation
from opendlp.service_layer.target_csv_import import import_targets_from_csv
from opendlp.service_layer.target_service import get_targets_for_assembly
from tests.fakes import FakeUnitOfWork

CHECK = "opendlp.entrypoints.blueprints.targets.check_targets_detailed"
START = "opendlp.entrypoints.blueprints.targets.start_db_select_task"

# Gender Male starts manual [5, 7]; the stubbed check suggests lowering the minimum to 3.
TARGETS_CSV = "feature,value,min,max\nGender,Male,5,7\nGender,Female,2,4\n"


@pytest.fixture(autouse=True)
def _mapped_domain_objects():
    """update_target_value writes via SQLAlchemy flag_modified, which needs mapped classes."""
    database.start_mappers()


@pytest.fixture
def assembly_with_targets(fake_store, admin_user):
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Targets Assembly",
            created_by_user_id=admin_user.id,
            question="What should we select?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            number_to_select=10,
        )
        assembly_id = assembly.id
    with FakeUnitOfWork(store=fake_store) as uow:
        update_csv_config(uow=uow, user_id=admin_user.id, assembly_id=assembly_id, settings_confirmed=True)
    with FakeUnitOfWork(store=fake_store) as uow:
        import_targets_from_csv(uow=uow, user_id=admin_user.id, assembly_id=assembly_id, csv_content=TARGETS_CSV)
    return assembly_id


def _ids(fake_store, admin_user, assembly_id, cat_name, val_name):
    with FakeUnitOfWork(store=fake_store) as uow:
        categories = get_targets_for_assembly(uow, admin_user.id, assembly_id)
    category = next(c for c in categories if c.name == cat_name)
    value = next(v for v in category.values if v.value == val_name)
    return category.id, value


def _value(fake_store, admin_user, assembly_id, cat_name, val_name):
    _cid, value = _ids(fake_store, admin_user, assembly_id, cat_name, val_name)
    return value


def _min_suggestion(suggested):
    return TargetAnnotation(
        level="suggestion",
        field="min",
        message=f"Suggested minimum: {suggested}",
        suggested_value=suggested,
    )


def _accept_url(assembly_id):
    return f"/backoffice/assembly/{assembly_id}/targets/accept-suggestions"


class TestAcceptOne:
    def test_applies_the_suggested_value_and_the_edited_comment(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        assembly_id = assembly_with_targets
        category_id, value = _ids(fake_store, admin_user, assembly_id, "Gender", "Male")
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )

        with patch(CHECK, return_value=check):
            response = logged_in_admin.post(
                _accept_url(assembly_id),
                data={
                    "scope": "one",
                    "category_id": str(category_id),
                    "value_id": str(value.value_id),
                    "field": "min",
                    "comment": "Accepted algorithm suggestion — minimum 5 → 3 — checked with team",
                    "then": "recheck",
                    "from": "selection",
                    "run_id": str(uuid.uuid4()),
                },
                follow_redirects=False,
            )

        assert response.status_code == 302
        assert "/targets/check" in response.headers["Location"]
        assert "from=selection" in response.headers["Location"]

        applied = _value(fake_store, admin_user, assembly_id, "Gender", "Male")
        assert applied.min == 3
        assert applied.max == 7
        assert applied.minmax_manual is True
        assert applied.comment == "Accepted algorithm suggestion — minimum 5 → 3 — checked with team"

    def test_falls_back_to_an_auto_comment_when_none_is_supplied(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        assembly_id = assembly_with_targets
        category_id, value = _ids(fake_store, admin_user, assembly_id, "Gender", "Male")
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )

        with patch(CHECK, return_value=check):
            logged_in_admin.post(
                _accept_url(assembly_id),
                data={
                    "scope": "one",
                    "category_id": str(category_id),
                    "value_id": str(value.value_id),
                    "field": "min",
                    "comment": "",
                    "then": "recheck",
                },
                follow_redirects=False,
            )

        applied = _value(fake_store, admin_user, assembly_id, "Gender", "Male")
        assert applied.min == 3
        assert "Accepted algorithm suggestion" in applied.comment

    def test_a_suggestion_the_check_no_longer_offers_changes_nothing(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        assembly_id = assembly_with_targets
        category_id, value = _ids(fake_store, admin_user, assembly_id, "Gender", "Male")
        empty = DetailedCheckResult(success=True, global_errors=[], annotations={})

        with patch(CHECK, return_value=empty):
            response = logged_in_admin.post(
                _accept_url(assembly_id),
                data={
                    "scope": "one",
                    "category_id": str(category_id),
                    "value_id": str(value.value_id),
                    "field": "min",
                    "then": "recheck",
                },
                follow_redirects=False,
            )

        assert response.status_code == 302
        with logged_in_admin.session_transaction() as session:
            flashes = [msg[1] for msg in session.get("_flashes", [])]
        assert any("no longer available" in msg for msg in flashes)

        unchanged = _value(fake_store, admin_user, assembly_id, "Gender", "Male")
        assert unchanged.min == 5


class TestAcceptAll:
    def test_applies_every_outstanding_suggestion(self, logged_in_admin, admin_user, fake_store, assembly_with_targets):
        assembly_id = assembly_with_targets
        check = DetailedCheckResult(
            success=False,
            global_errors=[],
            annotations={
                "Gender": {
                    "Male": [_min_suggestion(3)],
                    "Female": [
                        TargetAnnotation(
                            level="suggestion", field="max", message="Suggested maximum: 6", suggested_value=6
                        )
                    ],
                }
            },
        )

        with patch(CHECK, return_value=check):
            response = logged_in_admin.post(
                _accept_url(assembly_id),
                data={"scope": "all", "then": "recheck"},
                follow_redirects=False,
            )

        assert response.status_code == 302
        male = _value(fake_store, admin_user, assembly_id, "Gender", "Male")
        female = _value(fake_store, admin_user, assembly_id, "Gender", "Female")
        assert male.min == 3
        assert female.max == 6
        assert "Accepted algorithm suggestion" in male.comment
        assert "Accepted algorithm suggestion" in female.comment


class TestReRunGating:
    def test_accept_all_and_rerun_starts_a_selection_when_from_a_run(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        assembly_id = assembly_with_targets
        task_id = uuid.uuid4()
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )

        with patch(CHECK, return_value=check), patch(START, return_value=task_id) as start:
            response = logged_in_admin.post(
                _accept_url(assembly_id),
                data={"scope": "all", "then": "run", "from": "selection", "run_id": str(uuid.uuid4())},
                follow_redirects=False,
            )

        assert start.called
        assert response.status_code == 302
        assert f"current_selection={task_id}" in response.headers["Location"]

    def test_run_is_ignored_without_the_selection_provenance(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        assembly_id = assembly_with_targets
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )

        with patch(CHECK, return_value=check), patch(START) as start:
            response = logged_in_admin.post(
                _accept_url(assembly_id),
                data={"scope": "all", "then": "run"},  # no from=selection
                follow_redirects=False,
            )

        assert not start.called
        assert "/targets/check" in response.headers["Location"]


class TestCheckPageControls:
    def _check_url(self, assembly_id, query=""):
        return f"/backoffice/assembly/{assembly_id}/targets/check{query}"

    def test_renders_inline_accept_editor_and_rerun_when_from_a_run(
        self, logged_in_admin, fake_store, assembly_with_targets
    ):
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )
        with patch(CHECK, return_value=check):
            response = logged_in_admin.get(
                self._check_url(assembly_with_targets, f"?from=selection&run_id={uuid.uuid4()}")
            )

        assert response.status_code == 200
        assert b"accept-comment-" in response.data  # inline, editable comment field
        assert b"Accept all suggestions" in response.data
        assert b"re-run selection" in response.data

    def test_direct_visit_omits_the_rerun_button(self, logged_in_admin, fake_store, assembly_with_targets):
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )
        with patch(CHECK, return_value=check):
            response = logged_in_admin.get(self._check_url(assembly_with_targets))

        assert response.status_code == 200
        assert b"Accept all suggestions" in response.data
        assert b"re-run selection" not in response.data


class TestEditModeEntry:
    """ "Adjust targets" opens the editor, each suggestion under the row it would change."""

    def _check_url(self, assembly_id, query=""):
        return f"/backoffice/assembly/{assembly_id}/targets/check{query}"

    def _get(self, client, assembly_id, query):
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )
        with patch(CHECK, return_value=check):
            return client.get(self._check_url(assembly_id, query))

    def test_edit_flag_opens_the_editor_with_suggestions_filling_the_row(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        category_id, male = _ids(fake_store, admin_user, assembly_with_targets, "Gender", "Male")
        response = self._get(logged_in_admin, assembly_with_targets, f"?from=selection&run_id={uuid.uuid4()}&edit=1")

        html = response.data.decode()
        assert response.status_code == 200
        assert "editingAll: true" in html
        # The edit-form suggestion fills the row's own min and comment inputs in.
        prefix = f"bulk-{category_id}-{male.value_id}"
        assert f"&#34;{prefix}-min&#34;: 3" in html or f'"{prefix}-min": 3' in html
        assert f'data-comment-target="{prefix}-comment"' in html
        assert "Save & re-run selection" in html

    def test_without_the_edit_flag_the_page_opens_read_only(self, logged_in_admin, fake_store, assembly_with_targets):
        response = self._get(logged_in_admin, assembly_with_targets, f"?from=selection&run_id={uuid.uuid4()}")

        assert "editingAll: false" in response.data.decode()

    def test_save_and_rerun_is_only_offered_from_a_run(self, logged_in_admin, fake_store, assembly_with_targets):
        response = self._get(logged_in_admin, assembly_with_targets, "?edit=1")

        assert b"Save & re-run selection" not in response.data


class TestSaveAllFromSelection:
    def _post(self, client, fake_store, admin_user, assembly_id, extra):
        category_id, male = _ids(fake_store, admin_user, assembly_id, "Gender", "Male")
        prefix = f"cat[{category_id}]"
        data = {
            f"{prefix}[name]": "Gender",
            f"{prefix}[values][{male.value_id}][value]": "Male",
            f"{prefix}[values][{male.value_id}][min]": "3",
            f"{prefix}[values][{male.value_id}][max]": "7",
            f"{prefix}[values][{male.value_id}][comment]": "Accepted algorithm suggestion — minimum 5 → 3",
            **extra,
        }
        return client.post(f"/backoffice/assembly/{assembly_id}/targets/save-all", data=data)

    def test_save_and_rerun_saves_then_starts_a_selection(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        task_id = uuid.uuid4()
        with patch(START, return_value=task_id) as start:
            response = self._post(
                logged_in_admin,
                fake_store,
                admin_user,
                assembly_with_targets,
                {"from": "selection", "run_id": str(uuid.uuid4()), "then": "run"},
            )

        assert start.called
        assert f"current_selection={task_id}" in response.headers["Location"]
        assert _value(fake_store, admin_user, assembly_with_targets, "Gender", "Male").min == 3

    def test_plain_save_from_a_run_keeps_the_provenance(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        run_id = str(uuid.uuid4())
        with patch(START) as start:
            response = self._post(
                logged_in_admin, fake_store, admin_user, assembly_with_targets, {"from": "selection", "run_id": run_id}
            )

        assert not start.called
        location = response.headers["Location"]
        assert "/targets/check" in location
        assert "from=selection" in location
        assert run_id in location

    def test_run_is_ignored_without_the_selection_provenance(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        with patch(START) as start:
            response = self._post(logged_in_admin, fake_store, admin_user, assembly_with_targets, {"then": "run"})

        assert not start.called
        assert "/targets/check" in response.headers["Location"]


def _add_failed_run(fake_store, assembly_id, task_type):
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.selection_run_records.add(
            SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=uuid.uuid4(),
                status=SelectionRunStatus.FAILED,
                task_type=task_type,
                log_messages=["Task failed"],
                error_message="The targets cannot all be met from the pool.",
                completed_at=datetime.now(UTC),
            )
        )
        uow.commit()
        return uow.selection_run_records.get_by_assembly_id(assembly_id)[-1].task_id


class TestFailureViewLink:
    def _modal(self, client, assembly_id, run_id):
        return client.get(f"/backoffice/assembly/{assembly_id}/selection/db/modal-progress/{run_id}")

    def test_failed_initial_selection_offers_adjust_targets(self, logged_in_admin, fake_store, assembly_with_targets):
        run_id = _add_failed_run(fake_store, assembly_with_targets, SelectionTaskType.SELECT_FROM_DB)
        response = self._modal(logged_in_admin, assembly_with_targets, run_id)

        assert response.status_code == 200
        assert b"Adjust targets" in response.data
        assert b"from=selection" in response.data
        assert b"edit=1" in response.data

    def test_failed_replacement_run_has_no_adjust_targets_link(
        self, logged_in_admin, fake_store, assembly_with_targets
    ):
        run_id = _add_failed_run(fake_store, assembly_with_targets, SelectionTaskType.SELECT_REPLACEMENT_FROM_DB)
        response = self._modal(logged_in_admin, assembly_with_targets, run_id)

        assert response.status_code == 200
        assert b"Adjust targets" not in response.data
