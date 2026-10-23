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
ACCEPT_CHECK = "opendlp.service_layer.target_suggestions.check_targets_detailed"
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

        with patch(ACCEPT_CHECK, return_value=check):
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

        with patch(ACCEPT_CHECK, return_value=check):
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

        with patch(ACCEPT_CHECK, return_value=empty):
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

        with patch(ACCEPT_CHECK, return_value=check):
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

    def test_a_min_and_a_max_on_one_value_get_a_comment_each(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        max_suggestion = TargetAnnotation(
            level="suggestion", field="max", message="Suggested maximum: 9", suggested_value=9
        )
        check = DetailedCheckResult(
            success=False,
            global_errors=[],
            annotations={"Gender": {"Male": [max_suggestion, _min_suggestion(3)]}},
        )

        with patch(ACCEPT_CHECK, return_value=check):
            logged_in_admin.post(_accept_url(assembly_with_targets), data={"scope": "all", "then": "recheck"})

        male = _value(fake_store, admin_user, assembly_with_targets, "Gender", "Male")
        assert (male.min, male.max) == (3, 9)
        assert male.comment == (
            "Accepted algorithm suggestion — minimum 5 → 3; Accepted algorithm suggestion — maximum 7 → 9"
        )


class TestReRunGating:
    def test_accept_all_and_rerun_starts_a_selection_when_from_a_run(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        assembly_id = assembly_with_targets
        task_id = uuid.uuid4()
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )

        with patch(ACCEPT_CHECK, return_value=check), patch(START, return_value=task_id) as start:
            response = logged_in_admin.post(
                _accept_url(assembly_id),
                data={"scope": "all", "then": "run", "from": "selection", "run_id": str(uuid.uuid4())},
                follow_redirects=False,
            )

        assert start.called
        assert response.status_code == 302
        assert f"current_selection={task_id}" in response.headers["Location"]

    def test_accept_all_and_rerun_starts_a_real_selection_for_an_initial_run(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )

        with patch(ACCEPT_CHECK, return_value=check), patch(START, return_value=uuid.uuid4()) as start:
            logged_in_admin.post(
                _accept_url(assembly_with_targets),
                data={"scope": "all", "then": "run", "from": "selection", "run_id": str(uuid.uuid4())},
            )

        assert start.call_args.kwargs["test_selection"] is False

    def test_a_failed_test_selection_is_rerun_as_a_test_selection(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )

        with patch(ACCEPT_CHECK, return_value=check), patch(START, return_value=uuid.uuid4()) as start:
            logged_in_admin.post(
                _accept_url(assembly_with_targets),
                data={"scope": "all", "then": "run", "from": "selection", "run_id": str(uuid.uuid4()), "test": "1"},
            )

        assert start.call_args.kwargs["test_selection"] is True

    def test_recheck_after_accepting_keeps_the_test_flag(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )

        with patch(ACCEPT_CHECK, return_value=check):
            response = logged_in_admin.post(
                _accept_url(assembly_with_targets),
                data={"scope": "all", "then": "recheck", "from": "selection", "run_id": str(uuid.uuid4()), "test": "1"},
            )

        assert "test=1" in response.headers["Location"]

    def test_run_is_ignored_without_the_selection_provenance(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        assembly_id = assembly_with_targets
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )

        with patch(ACCEPT_CHECK, return_value=check), patch(START) as start:
            response = logged_in_admin.post(
                _accept_url(assembly_id),
                data={"scope": "all", "then": "run"},  # no from=selection
                follow_redirects=False,
            )

        assert not start.called
        assert "/targets/check" in response.headers["Location"]


def _flashes(client):
    with client.session_transaction() as session:
        return [msg[1] for msg in session.get("_flashes", [])]


class TestAcceptFailures:
    """What accept-suggestions does when the form or the assembly is not what it expects."""

    @pytest.mark.parametrize(
        "form",
        [
            {"category_id": "not-a-uuid", "value_id": "also-not"},
            {"category_id": str(uuid.uuid4()), "value_id": str(uuid.uuid4())},
        ],
        ids=["malformed ids", "unknown target"],
    )
    def test_a_target_that_cannot_be_found_changes_nothing(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets, form
    ):
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )

        with patch(ACCEPT_CHECK, return_value=check):
            response = logged_in_admin.post(
                _accept_url(assembly_with_targets),
                data={"scope": "one", "field": "min", "then": "recheck", **form},
            )

        assert "/targets/check" in response.headers["Location"]
        assert any("no longer available" in msg for msg in _flashes(logged_in_admin))
        assert _value(fake_store, admin_user, assembly_with_targets, "Gender", "Male").min == 5

    def test_rerun_waits_for_unconfirmed_selection_settings(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        with FakeUnitOfWork(store=fake_store) as uow:
            update_csv_config(
                uow=uow, user_id=admin_user.id, assembly_id=assembly_with_targets, settings_confirmed=False
            )
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )

        with patch(ACCEPT_CHECK, return_value=check), patch(START) as start:
            response = logged_in_admin.post(
                _accept_url(assembly_with_targets),
                data={"scope": "all", "then": "run", "from": "selection", "run_id": str(uuid.uuid4())},
            )

        assert not start.called
        assert "/targets/check" in response.headers["Location"]
        assert any("review and save the selection settings" in msg for msg in _flashes(logged_in_admin))
        # The accepted change is still saved; only the re-run waits.
        assert _value(fake_store, admin_user, assembly_with_targets, "Gender", "Male").min == 3

    def test_a_refused_rerun_keeps_the_accepted_change(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        _add_running_run(fake_store, assembly_with_targets)
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )

        with patch(ACCEPT_CHECK, return_value=check):
            response = logged_in_admin.post(
                _accept_url(assembly_with_targets),
                data={"scope": "all", "then": "run", "from": "selection", "run_id": str(uuid.uuid4())},
            )

        assert "/targets/check" in response.headers["Location"]
        assert any("Could not start selection task" in msg for msg in _flashes(logged_in_admin))
        assert _value(fake_store, admin_user, assembly_with_targets, "Gender", "Male").min == 3

    def test_an_unknown_assembly_is_not_found(self, logged_in_admin):
        response = logged_in_admin.post(_accept_url(uuid.uuid4()), data={"scope": "all", "then": "recheck"})

        assert response.status_code == 404

    def test_someone_who_may_not_manage_the_assembly_is_turned_away(
        self, logged_in_user, admin_user, fake_store, assembly_with_targets
    ):
        with patch(ACCEPT_CHECK) as check:
            response = logged_in_user.post(_accept_url(assembly_with_targets), data={"scope": "all", "then": "recheck"})

        assert not check.called
        assert response.status_code == 403
        assert _value(fake_store, admin_user, assembly_with_targets, "Gender", "Male").min == 5

    def test_an_unexpected_error_goes_back_to_the_targets_page(self, logged_in_admin, assembly_with_targets):
        with patch(ACCEPT_CHECK, side_effect=RuntimeError("boom")):
            response = logged_in_admin.post(
                _accept_url(assembly_with_targets), data={"scope": "all", "then": "recheck"}
            )

        assert response.headers["Location"].endswith(f"/backoffice/assembly/{assembly_with_targets}/targets")
        assert any("unexpected error" in msg for msg in _flashes(logged_in_admin))


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

    def test_a_run_id_that_is_not_a_uuid_is_dropped(self, logged_in_admin, fake_store, assembly_with_targets):
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )
        with patch(CHECK, return_value=check):
            response = logged_in_admin.get(
                self._check_url(assembly_with_targets, "?from=selection&run_id=x%27%2Balert(1)%2B%27")
            )

        html = response.data.decode()
        assert response.status_code == 200
        assert "alert(1)" not in html
        assert "re-run selection" not in html

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

    def test_a_test_run_is_offered_a_test_rerun_and_carries_the_flag(
        self, logged_in_admin, fake_store, assembly_with_targets
    ):
        response = self._get(
            logged_in_admin, assembly_with_targets, f"?from=selection&run_id={uuid.uuid4()}&test=1&edit=1"
        )

        html = response.data.decode()
        assert "Save & re-run test selection" in html
        assert "Accept all & re-run test selection" in html
        assert '<input type="hidden" name="test" value="1" />' in html

    def test_save_and_rerun_is_only_offered_from_a_run(self, logged_in_admin, fake_store, assembly_with_targets):
        response = self._get(logged_in_admin, assembly_with_targets, "?edit=1")

        assert b"Save & re-run selection" not in response.data


class TestSuggestionLayout:
    """A suggestion reads as belonging to the value above it, and points at the box it changes."""

    def _check_page(self, client, assembly_id):
        check = DetailedCheckResult(
            success=False, global_errors=[], annotations={"Gender": {"Male": [_min_suggestion(3)]}}
        )
        with patch(CHECK, return_value=check):
            response = client.get(f"/backoffice/assembly/{assembly_id}/targets/check?edit=1")
        assert response.status_code == 200
        return response.data.decode()

    @staticmethod
    def _table(html, block_id):
        start = html.index(f'id="{block_id}"')
        return html[start : html.index("</table>", start)]

    def test_read_only_view_groups_the_suggestion_with_its_value(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        category_id, _male = _ids(fake_store, admin_user, assembly_with_targets, "Gender", "Male")
        table = self._table(self._check_page(logged_in_admin, assembly_with_targets), f"category-{category_id}")

        groups = table.split("<tbody")[1:]
        male_group = next(g for g in groups if ">Male</td>" in g)
        female_group = next(g for g in groups if ">Female</td>" in g)
        # The dividing line is under the group, so it falls after the suggestion.
        assert male_group.startswith(' style="border-bottom: 1px solid var(--color-borders-dividers)"')
        assert "data-suggestion-row" in male_group
        assert "data-suggestion-row" not in female_group

    def test_read_only_view_outlines_the_box_the_suggestion_changes(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        category_id, _male = _ids(fake_store, admin_user, assembly_with_targets, "Gender", "Male")
        table = self._table(self._check_page(logged_in_admin, assembly_with_targets), f"category-{category_id}")

        assert table.count('data-suggested="true"') == 1
        # The outlined box is Male's minimum (5), not its maximum (7).
        outlined = table.split('data-suggested="true"')[1].split("</td>")[0]
        assert "<span>5</span>" in outlined
        assert "var(--color-warning-400)" in outlined

    def test_edit_form_draws_the_line_under_the_last_suggestion(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        category_id, male = _ids(fake_store, admin_user, assembly_with_targets, "Gender", "Male")
        _cid, female = _ids(fake_store, admin_user, assembly_with_targets, "Gender", "Female")
        table = self._table(self._check_page(logged_in_admin, assembly_with_targets), f"bulk-category-{category_id}")

        rows = table.split("<tr")
        male_row = next(r for r in rows if f'id="bulk-{category_id}-{male.value_id}-min"' in r)
        female_row = next(r for r in rows if f'id="bulk-{category_id}-{female.value_id}-min"' in r)
        suggestion_row = next(r for r in rows if "data-suggestion-row" in r)
        divider = "border-bottom: 1px solid var(--color-borders-dividers)"
        assert divider not in male_row.split(">")[0]
        assert divider in suggestion_row.split(">")[0]
        assert divider in female_row.split(">")[0]

    def test_edit_form_outlines_the_input_the_suggestion_changes(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        category_id, male = _ids(fake_store, admin_user, assembly_with_targets, "Gender", "Male")
        table = self._table(self._check_page(logged_in_admin, assembly_with_targets), f"bulk-category-{category_id}")

        assert table.count('data-suggested="true"') == 1
        outlined = table.split('data-suggested="true"')[1].split("</td>")[0]
        assert f'id="bulk-{category_id}-{male.value_id}-min"' in outlined


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

    def test_save_and_rerun_after_a_test_run_starts_a_test_selection(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        with patch(START, return_value=uuid.uuid4()) as start:
            self._post(
                logged_in_admin,
                fake_store,
                admin_user,
                assembly_with_targets,
                {"from": "selection", "run_id": str(uuid.uuid4()), "then": "run", "test": "1"},
            )

        assert start.call_args.kwargs["test_selection"] is True

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

    def test_a_refused_rerun_keeps_the_saved_edits(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        _add_running_run(fake_store, assembly_with_targets)

        response = self._post(
            logged_in_admin,
            fake_store,
            admin_user,
            assembly_with_targets,
            {"from": "selection", "run_id": str(uuid.uuid4()), "then": "run"},
        )

        assert "/targets/check" in response.headers["Location"]
        assert any("Could not start selection task" in msg for msg in _flashes(logged_in_admin))
        assert _value(fake_store, admin_user, assembly_with_targets, "Gender", "Male").min == 3

    def test_run_is_ignored_without_the_selection_provenance(
        self, logged_in_admin, admin_user, fake_store, assembly_with_targets
    ):
        with patch(START) as start:
            response = self._post(logged_in_admin, fake_store, admin_user, assembly_with_targets, {"then": "run"})

        assert not start.called
        assert "/targets/check" in response.headers["Location"]


def _add_running_run(fake_store, assembly_id):
    """A selection still running on the assembly, so a new one is refused."""
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.selection_run_records.add(
            SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=uuid.uuid4(),
                status=SelectionRunStatus.RUNNING,
                task_type=SelectionTaskType.SELECT_FROM_DB,
            )
        )
        uow.commit()


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

    def test_failed_test_selection_offers_adjust_targets_marked_as_a_test(
        self, logged_in_admin, fake_store, assembly_with_targets
    ):
        run_id = _add_failed_run(fake_store, assembly_with_targets, SelectionTaskType.TEST_SELECT_FROM_DB)
        response = self._modal(logged_in_admin, assembly_with_targets, run_id)

        assert response.status_code == 200
        assert b"Adjust targets" in response.data
        assert b"test=1" in response.data

    def test_failed_initial_selection_link_is_not_marked_as_a_test(
        self, logged_in_admin, fake_store, assembly_with_targets
    ):
        run_id = _add_failed_run(fake_store, assembly_with_targets, SelectionTaskType.SELECT_FROM_DB)
        response = self._modal(logged_in_admin, assembly_with_targets, run_id)

        assert b"test=1" not in response.data

    def test_failed_replacement_run_has_no_adjust_targets_link(
        self, logged_in_admin, fake_store, assembly_with_targets
    ):
        run_id = _add_failed_run(fake_store, assembly_with_targets, SelectionTaskType.SELECT_REPLACEMENT_FROM_DB)
        response = self._modal(logged_in_admin, assembly_with_targets, run_id)

        assert response.status_code == 200
        assert b"Adjust targets" not in response.data
