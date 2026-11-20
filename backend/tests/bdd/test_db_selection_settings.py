"""ABOUTME: BDD tests for the selection settings of a project held in OpenDLP
ABOUTME: Checks in a browser the settings dialog, what it shows and hides, and how selection waits for it"""

from playwright.sync_api import Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

from opendlp.service_layer import target_csv_import
from opendlp.service_layer.assembly_service import update_csv_config
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import Urls

scenarios("../../features/db-selection-settings.feature")

TARGETS_CSV = "feature,value,min,max\nGender,Male,1,1\nGender,Female,1,1"
RESPONDENTS_CSV = "external_id,Gender,Postcode\nM1,Male,AB1 2CD\nF1,Female,EF3 4GH\n"


@given("a user is logged in as an admin")
def user_logged_in_as_admin(admin_logged_in_page):
    """Background step: the fixture handles the login."""


@given("a database assembly whose selection settings are still to confirm", target_fixture="test_assembly")
def assembly_with_unconfirmed_settings(assembly_creator, admin_user, test_database):
    assembly = assembly_creator("DB Selection Settings Assembly", number_to_select=2)
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        update_csv_config(uow, admin_user.id, assembly.id, csv_id_column="external_id")
    with uow:
        target_csv_import.import_targets_from_csv(uow, admin_user.id, assembly.id, TARGETS_CSV)
    with uow:
        import_respondents_from_csv(uow, admin_user.id, assembly.id, RESPONDENTS_CSV, replace_existing=True)
    return assembly


@given("a database assembly whose selection settings are confirmed", target_fixture="test_assembly")
def assembly_with_confirmed_settings(assembly_creator, admin_user, test_database):
    assembly = assembly_with_unconfirmed_settings(assembly_creator, admin_user, test_database)
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        update_csv_config(uow, admin_user.id, assembly.id, settings_confirmed=True)
    return assembly


def _dialog(page: Page):
    return page.locator("#selection-settings-dialog")


def _cog(page: Page):
    return page.get_by_role("button", name="Selection settings", exact=True)


@when("the user visits the project details page")
def user_visits_details_page(admin_logged_in_page: Page, test_assembly):
    admin_logged_in_page.goto(Urls.backoffice_assembly_url(test_assembly.id))
    admin_logged_in_page.wait_for_load_state()


@when("the user visits the selection page")
def user_visits_selection_page(admin_logged_in_page: Page, test_assembly):
    admin_logged_in_page.goto(Urls.assembly_selection(test_assembly.id))
    admin_logged_in_page.wait_for_load_state()


@when("the user opens the selection settings")
def user_opens_settings(admin_logged_in_page: Page):
    _cog(admin_logged_in_page).click()
    expect(_dialog(admin_logged_in_page)).to_be_visible()


@when("the user follows the page's way to review the selection settings")
def user_follows_review_link(admin_logged_in_page: Page):
    admin_logged_in_page.locator("#selection-waiting").get_by_role("link", name="Review selection settings").click()


@when("the user ticks Check same address")
def user_ticks_check_same_address(admin_logged_in_page: Page):
    # The native checkbox is visually hidden behind a styled box, so click its label
    _dialog(admin_logged_in_page).get_by_text("Check same address", exact=True).click()
    expect(admin_logged_in_page.locator("#check_same_address")).to_be_checked()


@when("the user unticks Check same address")
def user_unticks_check_same_address(admin_logged_in_page: Page):
    _dialog(admin_logged_in_page).get_by_text("Check same address", exact=True).click()
    expect(admin_logged_in_page.locator("#check_same_address")).not_to_be_checked()


@when(parsers.parse('the user enters "{attributes}" as the address attributes'))
def user_enters_address_attributes(admin_logged_in_page: Page, attributes: str):
    admin_logged_in_page.get_by_label("Address attributes").fill(attributes)


@when("the user saves the selection settings")
def user_saves_settings(admin_logged_in_page: Page):
    _dialog(admin_logged_in_page).get_by_role("button", name="Save Settings").click()
    expect(admin_logged_in_page.get_by_text("Selection settings saved successfully")).to_be_visible()
    expect(_dialog(admin_logged_in_page)).to_have_count(0)


@when("the user tries to save the selection settings")
def user_tries_to_save_settings(admin_logged_in_page: Page):
    with admin_logged_in_page.expect_response(lambda response: response.url.endswith("/data/csv/settings")):
        _dialog(admin_logged_in_page).get_by_role("button", name="Save Settings").click()


@when("the user cancels the selection settings")
def user_cancels_settings(admin_logged_in_page: Page):
    _dialog(admin_logged_in_page).get_by_role("button", name="Cancel", exact=True).click()


@then("the selection settings dialog is open")
def settings_dialog_open(admin_logged_in_page: Page):
    expect(_dialog(admin_logged_in_page)).to_be_visible()
    expect(_dialog(admin_logged_in_page).get_by_role("heading", name="Selection settings")).to_be_visible()


@then("the selection settings dialog is closed")
def settings_dialog_closed(admin_logged_in_page: Page):
    expect(_dialog(admin_logged_in_page)).to_have_count(0)


@then("focus is on the selection settings cog")
def focus_on_cog(admin_logged_in_page: Page):
    expect(_cog(admin_logged_in_page)).to_be_focused()


@then(parsers.parse('the dialog says "{text}"'))
def dialog_says(admin_logged_in_page: Page, text: str):
    expect(_dialog(admin_logged_in_page)).to_contain_text(text)


@then("the settings do not ask for attributes to keep")
def settings_do_not_ask_for_attributes_to_keep(admin_logged_in_page: Page):
    settings = _dialog(admin_logged_in_page)
    expect(settings.get_by_text("Check same address", exact=True)).to_be_visible()
    expect(settings.get_by_text("Attributes to Keep")).to_have_count(0)


@then("the address attributes are hidden")
def address_attributes_hidden(admin_logged_in_page: Page):
    expect(admin_logged_in_page.get_by_label("Address attributes")).to_be_hidden()
    expect(admin_logged_in_page.get_by_text("Available respondent attributes")).to_be_hidden()


@then("the address attributes are shown")
def address_attributes_shown(admin_logged_in_page: Page):
    expect(admin_logged_in_page.get_by_label("Address attributes")).to_be_visible()
    expect(admin_logged_in_page.get_by_text("Available respondent attributes")).to_be_visible()


@then(parsers.parse('the address attributes are "{attributes}"'))
def address_attributes_are(admin_logged_in_page: Page, attributes: str):
    expect(admin_logged_in_page.get_by_label("Address attributes")).to_have_value(attributes)


@then("the page says selection is waiting for the selection settings")
def page_says_waiting_for_settings(admin_logged_in_page: Page):
    banner = admin_logged_in_page.locator("#selection-waiting")
    expect(banner).to_contain_text("Before you can run a selection:")
    expect(banner).to_contain_text("Review and save the selection settings.")


@then("the page does not say selection is waiting")
def page_does_not_say_waiting(admin_logged_in_page: Page):
    expect(admin_logged_in_page.locator("#selection-waiting")).to_have_count(0)


def _run_selection(page: Page):
    return page.locator("#initial-selection-step").get_by_role("button", name="Run Selection", exact=True)


@then("running a selection is not possible")
def running_not_possible(admin_logged_in_page: Page):
    expect(_run_selection(admin_logged_in_page)).to_be_disabled()


@then("running a selection is possible")
def running_possible(admin_logged_in_page: Page):
    expect(_run_selection(admin_logged_in_page)).to_be_enabled()


@then("the user is on the selection page")
def user_on_selection_page(admin_logged_in_page: Page, test_assembly):
    assert admin_logged_in_page.url.split("#")[0].split("?")[0] == Urls.assembly_selection(test_assembly.id)


@then("the user is on the project details page")
def user_on_details_page(admin_logged_in_page: Page, test_assembly):
    assert admin_logged_in_page.url.split("#")[0].split("?")[0] == Urls.backoffice_assembly_url(test_assembly.id)


@then(parsers.parse('the selection settings card says "{text}"'))
def settings_card_says(admin_logged_in_page: Page, text: str):
    expect(admin_logged_in_page.locator("#selection-settings")).to_contain_text(text)
