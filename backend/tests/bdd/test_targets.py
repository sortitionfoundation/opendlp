"""ABOUTME: BDD tests for target percentages, hand-set notes, bulk edit and reordering
ABOUTME: Exercises the full UI stack via Playwright for the paths covered by unit + e2e tests"""

import re
import uuid

from playwright.sync_api import Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.respondents import Respondent
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.service_layer.target_csv_import import import_targets_from_csv
from opendlp.service_layer.target_service import (
    add_target_value,
    create_target_category,
    get_targets_for_assembly,
    update_target_value,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import PLAYWRIGHT_TIMEOUT, Urls

scenarios("../../features/targets.feature")

# Nine values in the respondent data. With the first of them targeted, the eight
# that are left are more than the "not yet targeted" summary lists in full.
AGE_BANDS = ["16-19", "20-24", "25-29", "30-34", "35-44", "45-54", "55-64", "65-74", "75+"]


_target_assembly_ids: dict[str, str] = {}

# The assembly the scenario currently under way is about. The dict above outlives
# a single scenario, so steps that do not name their assembly use this instead.
_current_assembly_id: list[str] = []


def _targets_url(assembly_id: str) -> str:
    return f"{Urls.base}/backoffice/project/{assembly_id}/targets"


def _details_url_pattern(assembly_id: str) -> re.Pattern[str]:
    """The details tab, with or without the ?source= the tabs carry."""
    return re.compile(re.escape(f"{Urls.base}/backoffice/project/{assembly_id}") + r"(\?.*)?$")


def _row_for(page: Page, value: str):
    """The read-only table row whose first cell is this target value."""
    return page.locator("#target-categories tr").filter(has=page.get_by_role("cell", name=value, exact=False)).first


def _edit_row_for(page: Page, value: str):
    """The bulk-edit row whose value input holds this target value."""
    return page.locator("tr[data-value-row]").filter(has=page.locator(f'input[value="{value}"]')).first


def _edit_block_for(page: Page, name: str):
    """The bulk-edit category block whose name input holds this category name."""
    return page.locator("#bulk-categories > div").filter(has=page.locator(f'input[value="{name}"]')).first


def _visible(page: Page, text: str):
    """Matches of this text that are actually on screen.

    The page carries both the read-only view and the bulk edit form at once,
    with one of them hidden, so an unqualified text match finds the wrong copy.
    """
    return page.get_by_text(text).filter(visible=True)


@given(parsers.parse('there is an assembly with targets called "{title}"'))
def assembly_with_targets(title: str, assembly_creator, admin_user, test_database) -> None:
    """One category of two values at 50% each, against 20 seats."""
    assembly = assembly_creator(title, number_to_select=20)
    _target_assembly_ids[title] = str(assembly.id)
    _current_assembly_id[:] = [str(assembly.id)]

    with SqlAlchemyUnitOfWork(test_database) as uow:
        category = create_target_category(uow, admin_user.id, assembly.id, name="Gender")
        add_target_value(uow, admin_user.id, assembly.id, category.id, value="Male", percentage=50.0)
        add_target_value(uow, admin_user.id, assembly.id, category.id, value="Female", percentage=50.0)


@given(parsers.parse('there is an assembly with two target categories called "{title}"'))
def assembly_with_two_categories(title: str, assembly_creator, admin_user, test_database) -> None:
    assembly = assembly_creator(title, number_to_select=20)
    _target_assembly_ids[title] = str(assembly.id)
    _current_assembly_id[:] = [str(assembly.id)]

    with SqlAlchemyUnitOfWork(test_database) as uow:
        create_target_category(uow, admin_user.id, assembly.id, name="Gender")
        create_target_category(uow, admin_user.id, assembly.id, name="Age")


@given(parsers.parse('there is an assembly whose targets cannot all be met called "{title}"'))
def assembly_with_infeasible_targets(title: str, assembly_creator, admin_user, test_database) -> None:
    """Ten to select from ten older men and ten younger women.

    At least six young people are wanted, but every young person is a woman and
    at most five women may be chosen. The check suggests a young minimum of 5
    and an old maximum of 5.
    """
    assembly = assembly_creator(title, number_to_select=10)
    _target_assembly_ids[title] = str(assembly.id)
    _current_assembly_id[:] = [str(assembly.id)]

    with SqlAlchemyUnitOfWork(test_database) as uow:
        import_targets_from_csv(
            uow,
            admin_user.id,
            assembly.id,
            "feature,value,min,max\nGender,Male,5,6\nGender,Female,4,5\nAge,Young,6,7\nAge,Old,3,4\n",
        )
    with SqlAlchemyUnitOfWork(test_database) as uow:
        age = next(c for c in get_targets_for_assembly(uow, admin_user.id, assembly.id) if c.name == "Age")
        young = age.get_value("Young")
        update_target_value(
            uow, admin_user.id, assembly.id, age.id, young.value_id, value="Young", comment="From the census"
        )
    with SqlAlchemyUnitOfWork(test_database) as uow:
        stored = uow.assemblies.get(assembly.id)
        stored.csv = AssemblyCSV(assembly_id=assembly.id)
        stored.selection_settings = SelectionSettings(assembly_id=assembly.id, check_same_address=False)
        uow.respondents.bulk_add(
            [
                Respondent(assembly_id=assembly.id, external_id=f"m{i}", attributes={"Gender": "Male", "Age": "Old"})
                for i in range(10)
            ]
            + [
                Respondent(
                    assembly_id=assembly.id, external_id=f"f{i}", attributes={"Gender": "Female", "Age": "Young"}
                )
                for i in range(10)
            ]
        )
        uow.commit()


@given("the respondent data holds nine ages, one of them targeted")
def respondents_with_untargeted_ages(admin_user, test_database) -> None:
    """An Age category naming one band, against respondents spread over nine."""
    assembly_id = uuid.UUID(_current_assembly_id[0])
    with SqlAlchemyUnitOfWork(test_database) as uow:
        category = create_target_category(uow, admin_user.id, assembly_id, name="Age")
        add_target_value(uow, admin_user.id, assembly_id, category.id, value=AGE_BANDS[0], percentage=100.0)
        uow.respondents.bulk_add([
            Respondent(assembly_id=assembly_id, external_id=f"age-{i}", attributes={"Age": band})
            for i, band in enumerate(AGE_BANDS)
        ])
        uow.commit()


@given("I am signed in as an admin user")
def admin_signed_in(admin_logged_in_page: Page) -> None:
    """The ``admin_logged_in_page`` fixture handles the sign-in."""
    return


@given(parsers.parse('the "{value}" target was set by hand with the note "{note}"'))
def target_set_by_hand(value: str, note: str, admin_user, test_database) -> None:
    assembly_id = uuid.UUID(_current_assembly_id[0])
    with SqlAlchemyUnitOfWork(test_database) as uow:
        category = get_targets_for_assembly(uow, admin_user.id, assembly_id)[0]
        target_value = category.get_value(value)
        update_target_value(
            uow,
            admin_user.id,
            assembly_id,
            category.id,
            target_value.value_id,
            value=value,
            min_count=12,
            max_count=13,
            comment=note,
        )


@when(parsers.parse('I open the targets page for "{title}"'))
def open_targets_page(admin_logged_in_page: Page, title: str) -> None:
    admin_logged_in_page.goto(_targets_url(_target_assembly_ids[title]))


@when(parsers.parse('I adjust the targets for "{title}" after a failed test selection'))
def adjust_targets_after_failed_selection(admin_logged_in_page: Page, title: str, test_database) -> None:
    """Where "Adjust targets" on a failed test selection leads: the check, open in the editor."""
    assembly_id = uuid.UUID(_target_assembly_ids[title])
    run_id = uuid.uuid4()
    with SqlAlchemyUnitOfWork(test_database) as uow:
        uow.selection_run_records.add(
            SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=run_id,
                status=SelectionRunStatus.FAILED,
                task_type=SelectionTaskType.TEST_SELECT_FROM_DB,
            )
        )
        uow.commit()
    admin_logged_in_page.goto(f"{_targets_url(str(assembly_id))}/check?from=selection&run_id={run_id}&edit=1")


@when(parsers.parse('I accept the suggestion "{message}"'))
def accept_suggestion(admin_logged_in_page: Page, message: str) -> None:
    row = admin_logged_in_page.locator("tr[data-suggestion-row]").filter(has_text=message).filter(visible=True)
    row.get_by_role("button", name="Accept").click()


@when("I undo the accepted suggestion")
def undo_accepted_suggestion(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.get_by_role("button", name="Undo").click()


@when("I accept all the suggestions")
def accept_all_suggestions(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.get_by_role("button", name="Accept all suggestions").click()


@when("I choose to edit all targets")
def choose_edit_all(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.get_by_role("button", name="Edit targets").click()


@when("I save all targets")
def save_all(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.get_by_role("button", name="Save", exact=True).click()


@when(parsers.parse('I link the "{value}" target back to its percentage'))
def relink_target(admin_logged_in_page: Page, value: str) -> None:
    _edit_row_for(admin_logged_in_page, value).get_by_role(
        "button", name="Recalculate min and max from the percentage"
    ).click()


@when(parsers.parse('I move the "{name}" category down'))
def move_category_down(admin_logged_in_page: Page, name: str) -> None:
    _edit_block_for(admin_logged_in_page, name).get_by_role("button", name="Move down").first.click()


@when("I try to leave for the assembly details")
def click_details_tab(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.get_by_role("tab", name="Project Details").click()


@when("I choose to keep editing")
def keep_editing(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.get_by_role("button", name="Keep editing").click()


@when("I discard the edits from the save bar")
def discard_from_save_bar(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.locator(".wizard-footer").get_by_role("button", name="Discard changes").click()


@when("I choose to discard the changes")
def discard_changes(admin_logged_in_page: Page) -> None:
    """The one in the dialog - the save bar's button of the same name opens it."""
    admin_logged_in_page.get_by_role("alertdialog").get_by_role("button", name="Discard changes").click()


@then("I should still be on the targets page")
def still_on_targets(admin_logged_in_page: Page) -> None:
    expect(admin_logged_in_page).to_have_url(_targets_url(_current_assembly_id[-1]), timeout=PLAYWRIGHT_TIMEOUT)


@then("I should be on the assembly details page")
def on_details_page(admin_logged_in_page: Page) -> None:
    """Named positively: "not the targets page" also passes on an error page."""
    expect(admin_logged_in_page).to_have_url(_details_url_pattern(_current_assembly_id[-1]), timeout=PLAYWRIGHT_TIMEOUT)


@when(parsers.parse('I add a target called "{name}"'))
def add_category_via_dialog(admin_logged_in_page: Page, name: str) -> None:
    """The one flow, from either view: name it in the dialog and it lands in the form."""
    admin_logged_in_page.get_by_role("button", name="Add target").click()
    admin_logged_in_page.locator("#add-target-name").fill(name)
    admin_logged_in_page.get_by_role("button", name="Add", exact=True).click()


@when(parsers.parse('I add a target value called "{value}" with percentage "{percentage}"'))
def add_target_value_in_bulk_form(admin_logged_in_page: Page, value: str, percentage: str) -> None:
    """Into the last category block, which is the one most recently added."""
    block = admin_logged_in_page.locator("#bulk-categories > div").last
    row = _blank_or_new_row(block)
    row.locator('[data-field="value"]').fill(value)
    row.locator('[data-field="percentage"]').fill(percentage)


def _blank_or_new_row(block):
    """The block's last row if it is still blank, otherwise one added for the purpose.

    A target added through the dialog arrives with one empty row, so the first
    value goes into that rather than leaving it behind to fail validation.
    """
    last = block.locator("tr[data-value-row]").last
    if last.count() and last.locator('[data-field="value"]').input_value() == "":
        return last
    block.get_by_role("button", name="Add value", exact=True).click()
    return block.locator("tr[data-value-row]").last


@when("I add the values found in the respondent data")
def add_missing_values(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.get_by_role("button", name="Add values found in respondent data").click()


@when(parsers.parse('I delete the "{value}" target value'))
def delete_target_value_in_bulk_form(admin_logged_in_page: Page, value: str) -> None:
    _edit_row_for(admin_logged_in_page, value).get_by_role("button", name="Delete value").click()


@when(parsers.parse('I take back the deletion of the "{value}" target value'))
def undo_delete_target_value(admin_logged_in_page: Page, value: str) -> None:
    _edit_row_for(admin_logged_in_page, value).get_by_role("button", name="Undo").click()


@when(parsers.parse('I delete the "{name}" category'))
def delete_category_in_bulk_form(admin_logged_in_page: Page, name: str) -> None:
    _edit_block_for(admin_logged_in_page, name).get_by_role("button", name="Delete target").click()


@when(parsers.parse('I set the "{value}" percentage to "{percentage}"'))
def set_percentage_in_bulk_form(admin_logged_in_page: Page, value: str, percentage: str) -> None:
    _edit_row_for(admin_logged_in_page, value).locator('[data-field="percentage"]').fill(percentage)


@when(parsers.parse('I set the "{value}" min to "{minimum}" and max to "{maximum}"'))
def set_min_max_in_bulk_form(admin_logged_in_page: Page, value: str, minimum: str, maximum: str) -> None:
    row = _edit_row_for(admin_logged_in_page, value)
    row.locator('[data-field="min"]').fill(minimum)
    row.locator('[data-field="max"]').fill(maximum)


@then(parsers.parse('the "{name}" category should be on screen with one blank value'))
def new_category_ready_to_fill_in(admin_logged_in_page: Page, name: str) -> None:
    block = _edit_block_for(admin_logged_in_page, name)
    expect(block).to_be_in_viewport(timeout=PLAYWRIGHT_TIMEOUT)
    rows = block.locator("tr[data-value-row]")
    expect(rows).to_have_count(1, timeout=PLAYWRIGHT_TIMEOUT)
    expect(rows.locator('[data-field="value"]')).to_have_value("", timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the "{value}" edit row should show min "{minimum}" and max "{maximum}"'))
def edit_row_shows_min_max(admin_logged_in_page: Page, value: str, minimum: str, maximum: str) -> None:
    row = _edit_row_for(admin_logged_in_page, value)
    expect(row.locator('[data-field="min"]')).to_have_value(minimum, timeout=PLAYWRIGHT_TIMEOUT)
    expect(row.locator('[data-field="max"]')).to_have_value(maximum, timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the "{value}" edit row comment should be "{comment}"'))
def edit_row_comment(admin_logged_in_page: Page, value: str, comment: str) -> None:
    row = _edit_row_for(admin_logged_in_page, value)
    expect(row.locator('textarea[name$="[comment]"]')).to_have_value(comment, timeout=PLAYWRIGHT_TIMEOUT)


THREE_LINE_COMMENT = "first line\nsecond line\nthird line"


def _comment_box(page: Page, value: str):
    return _edit_row_for(page, value).locator('textarea[name$="[comment]"]')


@when(parsers.parse('I write a three line comment on the "{value}" target value'))
def write_three_line_comment(admin_logged_in_page: Page, value: str) -> None:
    _comment_box(admin_logged_in_page, value).fill(THREE_LINE_COMMENT)


@when(parsers.parse('I move on from the "{value}" comment box'))
def leave_comment_box(admin_logged_in_page: Page, value: str) -> None:
    _comment_box(admin_logged_in_page, value).blur()


@then(parsers.parse('the "{value}" comment box should show every line'))
def comment_box_shows_every_line(admin_logged_in_page: Page, value: str) -> None:
    """Nothing scrolled out of sight: the box is as tall as the text in it."""
    box = _comment_box(admin_logged_in_page, value)
    expect(box).to_be_focused(timeout=PLAYWRIGHT_TIMEOUT)
    hidden = box.evaluate("el => el.scrollHeight - el.clientHeight")
    assert hidden <= 1, f"{hidden}px of the comment is out of sight"


@then(parsers.parse('the "{value}" comment box should be one line high'))
def comment_box_is_one_line(admin_logged_in_page: Page, value: str) -> None:
    """As tall as the single-line value input beside it, so the row keeps its shape."""
    row = _edit_row_for(admin_logged_in_page, value)
    box_height = _comment_box(admin_logged_in_page, value).bounding_box()["height"]
    input_height = row.locator('[data-field="value"]').bounding_box()["height"]
    assert abs(box_height - input_height) <= 2, f"comment box is {box_height}px, value input {input_height}px"
    expect(_comment_box(admin_logged_in_page, value)).to_have_attribute("title", THREE_LINE_COMMENT)


@then(parsers.parse('the "{value}" comment should read as three lines'))
def comment_reads_as_three_lines(admin_logged_in_page: Page, value: str) -> None:
    comment = _row_for(admin_logged_in_page, value).get_by_text("first line")
    expect(comment).to_have_css("white-space", "pre-line", timeout=PLAYWRIGHT_TIMEOUT)
    assert comment.inner_text().splitlines() == ["first line", "second line", "third line"]


@then(parsers.parse('the focus should be on "{label}" for "{message}"'))
def focus_on_button_for(admin_logged_in_page: Page, label: str, message: str) -> None:
    """Every suggestion's buttons share a name; the suggestion describing them tells them apart."""
    focused = admin_logged_in_page.locator(":focus")
    expect(focused).to_have_accessible_name(label, timeout=PLAYWRIGHT_TIMEOUT)
    expect(focused).to_have_accessible_description(message, timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the "{value}" edit row should show the error "{message}"'))
def edit_row_shows_error(admin_logged_in_page: Page, value: str, message: str) -> None:
    row = _edit_row_for(admin_logged_in_page, value)
    expect(row.get_by_text(message)).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('I should see the percentage total "{total}"'))
def see_percentage_total(admin_logged_in_page: Page, total: str) -> None:
    expect(_visible(admin_logged_in_page, total).first).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the "{value}" target should show min "{minimum}" and max "{maximum}"'))
def target_shows_min_max(admin_logged_in_page: Page, value: str, minimum: str, maximum: str) -> None:
    row = _row_for(admin_logged_in_page, value)
    expect(row).to_contain_text(minimum, timeout=PLAYWRIGHT_TIMEOUT)
    expect(row).to_contain_text(maximum, timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the "{value}" target should be marked as manually modified'))
def target_marked_manual(admin_logged_in_page: Page, value: str) -> None:
    _expect_provenance(admin_logged_in_page, value, "Manually modified", "Auto calculated")


@then(parsers.parse('the "{value}" target should be marked as auto calculated'))
def target_marked_automatic(admin_logged_in_page: Page, value: str) -> None:
    _expect_provenance(admin_logged_in_page, value, "Auto calculated", "Manually modified")


def _expect_provenance(page: Page, value: str, wanted: str, unwanted: str) -> None:
    """Both the min and the max cell of this row carry the one mark, and not the other."""
    row = _row_for(page, value)
    expect(row.locator(f'[title="{wanted}"]')).to_have_count(2, timeout=PLAYWRIGHT_TIMEOUT)
    expect(row.locator(f'[title="{unwanted}"]')).to_have_count(0, timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('I should see "{text}"'))
def should_see(admin_logged_in_page: Page, text: str) -> None:
    expect(_visible(admin_logged_in_page, text).first).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('I should not see "{text}"'))
def should_not_see(admin_logged_in_page: Page, text: str) -> None:
    expect(_visible(admin_logged_in_page, text)).to_have_count(0, timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('I should see the "{label}" button'))
def should_see_button(admin_logged_in_page: Page, label: str) -> None:
    button = admin_logged_in_page.get_by_role("button", name=label, exact=True).filter(visible=True)
    expect(button.first).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('I should not see the "{label}" button'))
def should_not_see_button(admin_logged_in_page: Page, label: str) -> None:
    button = admin_logged_in_page.get_by_role("button", name=label, exact=True).filter(visible=True)
    expect(button).to_have_count(0, timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('there should be no "{value}" target value'))
def no_such_target_value(admin_logged_in_page: Page, value: str) -> None:
    cells = admin_logged_in_page.locator("#target-categories").get_by_role("cell", name=value, exact=True)
    expect(cells).to_have_count(0, timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('there should be no "{name}" category'))
def no_such_category(admin_logged_in_page: Page, name: str) -> None:
    headings = admin_logged_in_page.locator("#target-categories").get_by_role("heading", name=name, exact=True)
    expect(headings).to_have_count(0, timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the bulk edit total should show "{total}"'))
def bulk_edit_total(admin_logged_in_page: Page, total: str) -> None:
    expect(admin_logged_in_page.locator("#bulk-categories tfoot").first).to_contain_text(
        total, timeout=PLAYWRIGHT_TIMEOUT
    )


@then("I should see the bulk edit form")
def see_bulk_edit_form(admin_logged_in_page: Page) -> None:
    expect(admin_logged_in_page.locator("#save-all-form")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the "{second}" category should appear after the "{first}" category'))
def category_order_after(admin_logged_in_page: Page, first: str, second: str) -> None:
    category_order(admin_logged_in_page, first, second)


@then(parsers.parse('the "{first}" category should appear before the "{second}" category'))
def category_order(admin_logged_in_page: Page, first: str, second: str) -> None:
    headings = admin_logged_in_page.get_by_role("heading").all_text_contents()
    names = [h.strip() for h in headings]
    assert names.index(first) < names.index(second), f"expected {first} before {second} in {names}"
