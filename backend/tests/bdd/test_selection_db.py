"""ABOUTME: BDD steps running selection.feature against a project whose data is held in OpenDLP
ABOUTME: Drives the data source and selection settings dialogs, and the Selection tab's progress and replacement dialogs"""

from pathlib import Path

from playwright.sync_api import Locator, Page, expect
from pytest_bdd import given, scenarios, then, when

from opendlp.domain.assembly import Assembly
from opendlp.domain.value_objects import RespondentStatus
from opendlp.service_layer import target_csv_import
from opendlp.service_layer.assembly_service import update_csv_config, update_selection_settings
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.bdd.config import Urls

"""
Note this file is one of several that run selection.feature. This one is for when the
respondents and the targets are held in the database. test_selection_manual_gsheet.py is
for when they are in a Google Sheets spreadsheet.

The idea is that the feature file describes the process at a high level. So we can have
multiple implementations that use the exact same feature file.
"""

scenarios("../../features/selection.feature")

EXAMPLES = Path(__file__).parent.parent.parent / "static" / "examples"
TARGETS_FILE = EXAMPLES / "example-targets.csv"
RESPONDENTS_FILE = EXAMPLES / "example-respondents.csv"
# what the example targets file holds
NUM_TARGETS = 4
NUM_TARGET_VALUES = 18
NUMBER_TO_SELECT = 30


def _data_source_dialog(page: Page) -> Locator:
    return page.get_by_role("dialog", name="Data source settings")


def _selection_settings_dialog(page: Page) -> Locator:
    return page.locator("#selection-settings-dialog")


def _progress_modal(page: Page) -> Locator:
    return page.get_by_role("dialog", name="Task progress")


def _replacement_modal(page: Page) -> Locator:
    return page.get_by_role("dialog", name="Replacement Selection")


def _open_selection_tab(page: Page, assembly: Assembly) -> None:
    page.goto(Urls.backoffice_assembly_url(str(assembly.id)))
    page.get_by_role("tab", name="Select and Replace", exact=True).click()
    expect(page).to_have_url(Urls.assembly_selection(assembly.id))


def _upload(page: Page, kind: str, path: Path) -> None:
    dialog = _data_source_dialog(page)
    dialog.locator(f"#project-{kind}-source").select_option("csv")
    dialog.locator(f"#project-{kind}-file").set_input_files(path)
    with page.expect_response(lambda response: response.url.endswith(f"/upload-{kind}")):
        dialog.get_by_role("button", name=f"Upload {kind}", exact=True).click()


def _run_initial_selection(page: Page, assembly: Assembly) -> None:
    _open_selection_tab(page, assembly)
    page.get_by_role("button", name="Run Selection", exact=True).click()
    expect(_progress_modal(page).get_by_text("Task completed successfully.")).to_be_visible(timeout=30_000)


def _withdraw_one_selected_person(test_database, assembly: Assembly) -> None:
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        selected = [
            respondent
            for respondent in uow.respondents.get_by_assembly_id(assembly.id)
            if respondent.selection_status == RespondentStatus.SELECTED
        ]
        assert len(selected) == NUMBER_TO_SELECT
        selected[0].selection_status = RespondentStatus.WITHDRAWN
        uow.commit()


def _open_replacement_dialog_after_a_withdrawal(page: Page, test_database, assembly: Assembly) -> None:
    """Replacements fill the place of someone who withdrew, so first there is a selection and a withdrawal."""
    _run_initial_selection(page, assembly)
    _withdraw_one_selected_person(test_database, assembly)
    page.goto(Urls.assembly_selection(assembly.id))
    page.get_by_role("button", name="Select replacements").click()
    expect(_replacement_modal(page)).to_be_visible()


def _set_selection_options(test_database, admin_user, assembly: Assembly) -> None:
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        update_selection_settings(uow, admin_user.id, assembly.id, check_same_address=False)
    with uow:
        update_csv_config(uow, admin_user.id, assembly.id, csv_id_column="unique_id", settings_confirmed=True)
    with uow:
        target_csv_import.import_targets_from_csv(uow, admin_user.id, assembly.id, TARGETS_FILE.read_text())
    with uow:
        import_respondents_from_csv(
            uow, admin_user.id, assembly.id, RESPONDENTS_FILE.read_text(), replace_existing=True
        )


@given("people are registered")
def _():
    """people are registered."""
    # For this version, the respondents' details are in a CSV file, to be uploaded


@given("the assembly is set up", target_fixture="assembly_to_select")
def _(assembly_creator):
    """the assembly is set up, with nothing yet said about its data."""
    return assembly_creator("Assembly to select", number_to_select=NUMBER_TO_SELECT)


@when("I open the Assembly")
def _(admin_logged_in_page: Page, assembly_to_select):
    """I open the Assembly, and the settings for where its data comes from."""
    page = admin_logged_in_page
    page.goto(Urls.backoffice_assembly_url(str(assembly_to_select.id)))
    page.get_by_role("button", name="Data source settings", exact=True).click()
    expect(_data_source_dialog(page)).to_be_visible()


@then("I can specify the source of the respondents data")
def _(page: Page):
    """I can specify the source of the respondents data, by uploading a CSV file."""
    _upload(page, "respondents", RESPONDENTS_FILE)
    expect(_data_source_dialog(page)).to_contain_text("100 respondents uploaded")


@then("I can specify the categories and targets")
def _(page: Page):
    """I can specify the categories and targets, by uploading a CSV file."""
    _upload(page, "targets", TARGETS_FILE)
    expect(_data_source_dialog(page)).to_contain_text(f"{NUM_TARGETS} targets uploaded")


@then("I can configure the options for selection")
def _(page: Page):
    """I can configure the options for selection, which have a dialog of their own once the data is in."""
    with page.expect_response(lambda response: response.url.endswith("/data-source/save")):
        _data_source_dialog(page).get_by_role("button", name="Save", exact=True).click()
    expect(_data_source_dialog(page)).to_have_count(0)
    page.get_by_role("button", name="Selection settings", exact=True).click()
    dialog = _selection_settings_dialog(page)
    expect(dialog).to_be_visible()
    check_same_address = page.locator("#check_same_address")
    if check_same_address.is_checked():
        # the box itself is drawn by its label, so that is what takes the click
        dialog.get_by_text("Check same address", exact=True).click()
    expect(check_same_address).not_to_be_checked()


@then("I can save the options")
def _(page: Page, assembly_to_select, test_database):
    """I can save the options, and selection is then no longer waiting for them."""
    _selection_settings_dialog(page).get_by_role("button", name="Save Settings").click()
    expect(page.get_by_text("Selection settings saved successfully")).to_be_visible()
    expect(_selection_settings_dialog(page)).to_have_count(0)
    page.goto(Urls.assembly_selection(assembly_to_select.id))
    expect(page.locator("#selection-waiting")).to_have_count(0)
    expect(page.get_by_role("button", name="Run Selection", exact=True)).to_be_enabled()


@given("the selection options are set")
def _(assembly_to_select, admin_user, test_database):
    """the options are set, and the targets and respondents are in the database."""
    _set_selection_options(test_database, admin_user, assembly_to_select)


@when("I check the data")
def _(admin_logged_in_page: Page, assembly_to_select: Assembly):
    """I check the data, which for data held in OpenDLP is a test selection."""
    page = admin_logged_in_page
    _open_selection_tab(page, assembly_to_select)
    page.get_by_role("button", name="Run Test Selection", exact=True).click()
    expect(_progress_modal(page)).to_be_visible()


@when("I start the selection")
def _(admin_logged_in_page: Page, assembly_to_select: Assembly):
    """I start the selection, from the Selection tab."""
    page = admin_logged_in_page
    _open_selection_tab(page, assembly_to_select)
    page.get_by_role("button", name="Run Selection", exact=True).click()
    expect(_progress_modal(page)).to_be_visible()


@then("I am told the number of categories and category values")
def _(page: Page):
    """I am told the number of categories and category values.

    A run says so in its messages. The replacement dialog instead lists every
    category value, with how many of each are still needed.
    """
    if _replacement_modal(page).count():
        expect(_replacement_modal(page).get_by_label("Minimum still needed for")).to_have_count(NUM_TARGET_VALUES)
        return
    modal = _progress_modal(page)
    told = modal.get_by_text(f"Found {NUM_TARGETS} targets with {NUM_TARGET_VALUES} values").first
    expect(told).to_be_attached(timeout=30_000)
    expect(modal.get_by_text("Task completed successfully.")).to_be_visible(timeout=30_000)
    # A finished task's messages are collapsed
    modal.locator("details:not([open]) > summary").filter(has_text="Messages").click()
    expect(told).to_be_visible()


@then("I am told selection has completed")
def _(page: Page):
    """I am told selection has completed."""
    expect(_progress_modal(page).get_by_text("Task completed successfully.")).to_be_visible(timeout=30_000)


@when("I initialise the replacements process")
def _(admin_logged_in_page: Page, assembly_to_select: Assembly, test_database):
    """I initialise the replacements process, once someone selected has withdrawn."""
    _open_replacement_dialog_after_a_withdrawal(admin_logged_in_page, test_database, assembly_to_select)


@then("I am asked for the number to select")
def _(page: Page):
    """I am asked for the number to select: the dialog works it out, and lets me change it."""
    modal = _replacement_modal(page)
    expect(modal).to_contain_text("1 place is to be filled")
    modal.get_by_role("button", name="Change the number of replacements").click()
    number_input = modal.get_by_label("Number of replacements to select")
    expect(number_input).to_be_visible()
    expect(number_input).to_have_value("1")


@given("the replacements process is initialised")
def _(admin_logged_in_page: Page, assembly_to_select: Assembly, admin_user, test_database):
    """the replacements process is initialised."""
    _set_selection_options(test_database, admin_user, assembly_to_select)
    _open_replacement_dialog_after_a_withdrawal(admin_logged_in_page, test_database, assembly_to_select)


@given("I have set the number to select")
def _(page: Page):
    """I have set the number to select."""
    modal = _replacement_modal(page)
    modal.get_by_role("button", name="Change the number of replacements").click()
    modal.get_by_label("Number of replacements to select").fill("1")


@when("I start the replacements")
def _(page: Page):
    """I start the replacements."""
    _replacement_modal(page).get_by_role("button", name="Run Replacement Selection").click()
