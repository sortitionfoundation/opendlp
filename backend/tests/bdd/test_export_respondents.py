"""ABOUTME: BDD tests for exporting respondents to CSV via the export modal
ABOUTME: Drives the full UI stack with Playwright, capturing the CSV download"""

import pathlib

from playwright.sync_api import Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

from opendlp.service_layer.assembly_service import update_csv_config
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import Urls

scenarios("../../features/export-respondents.feature")


@given(
    parsers.parse('there is an assembly with respondents ready to export called "{title}"'),
    target_fixture="export_assembly_id",
)
def assembly_ready_to_export(title: str, assembly_creator, admin_user, test_database) -> str:
    assembly = assembly_creator(title, number_to_select=20)

    csv_content = "external_id,first_name,consent,eligible\nR001,Alice,true,true\nR002,Bob,true,true\n"
    uow = SqlAlchemyUnitOfWork(test_database)
    import_respondents_from_csv(uow, admin_user.id, assembly.id, csv_content, replace_existing=True)
    # Set the CSV config so the respondents page shows the CSV data source (and the Export button).
    update_csv_config(uow, admin_user.id, assembly.id, csv_id_column="external_id")
    return str(assembly.id)


@given("I am signed in as an admin user")
def admin_signed_in(admin_logged_in_page: Page) -> None:
    """The ``admin_logged_in_page`` fixture handles the sign-in."""


@when(parsers.parse('I open the respondents page for "{title}"'))
def open_respondents_page(admin_logged_in_page: Page, title: str, export_assembly_id: str) -> None:
    admin_logged_in_page.goto(f"{Urls.base}/backoffice/assembly/{export_assembly_id}/respondents?source=csv")
    admin_logged_in_page.wait_for_load_state("networkidle")


@when("I open the export modal")
def open_export_modal(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.get_by_role("button", name="Export").first.click()
    expect(admin_logged_in_page.locator("#export-modal-container select#export-status")).to_be_visible()


@then("a CSV download starts when I run the export", target_fixture="downloaded_csv")
def run_export_download(admin_logged_in_page: Page) -> str:
    with admin_logged_in_page.expect_download() as download_info:
        admin_logged_in_page.locator("#export-modal-container button[type=submit]").click()
    download = download_info.value
    path = download.path()
    return pathlib.Path(path).read_text(encoding="utf-8")


@then("the downloaded CSV contains the respondent ids")
def csv_contains_ids(downloaded_csv: str) -> None:
    assert "R001" in downloaded_csv
    assert "R002" in downloaded_csv
    assert "selection_status" in downloaded_csv
