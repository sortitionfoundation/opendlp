"""ABOUTME: BDD tests for the selection settings of a project held in OpenDLP
ABOUTME: Checks in a browser that the address attributes show only while the address check is ticked"""

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


@when("the user visits the selection page")
def user_visits_selection_page(admin_logged_in_page: Page, test_assembly):
    admin_logged_in_page.goto(Urls.assembly_selection(test_assembly.id))
    admin_logged_in_page.wait_for_load_state()


@when("the user ticks Check Same Address")
def user_ticks_check_same_address(admin_logged_in_page: Page):
    # The native checkbox is visually hidden behind a styled box, so click its label
    admin_logged_in_page.locator("#selection-settings").get_by_text("Check Same Address", exact=True).click()
    expect(admin_logged_in_page.locator("#check_same_address")).to_be_checked()


@when("the user unticks Check Same Address")
def user_unticks_check_same_address(admin_logged_in_page: Page):
    admin_logged_in_page.locator("#selection-settings").get_by_text("Check Same Address", exact=True).click()
    expect(admin_logged_in_page.locator("#check_same_address")).not_to_be_checked()


@when(parsers.parse('the user enters "{attributes}" as the address attributes'))
def user_enters_address_attributes(admin_logged_in_page: Page, attributes: str):
    admin_logged_in_page.get_by_label("Address Attributes").fill(attributes)


@when("the user saves the selection settings")
def user_saves_settings(admin_logged_in_page: Page):
    admin_logged_in_page.get_by_role("button", name="Save Settings").click()
    admin_logged_in_page.wait_for_load_state()
    expect(admin_logged_in_page.get_by_text("Selection settings saved successfully")).to_be_visible()


@when("the user opens the selection settings")
def user_opens_settings(admin_logged_in_page: Page):
    admin_logged_in_page.locator("#selection-settings > summary").click()


@then("the settings do not ask for attributes to keep")
def settings_do_not_ask_for_attributes_to_keep(admin_logged_in_page: Page):
    settings = admin_logged_in_page.locator("#selection-settings")
    expect(settings.get_by_text("Check Same Address", exact=True)).to_be_visible()
    expect(settings.get_by_text("Attributes to Keep")).to_have_count(0)


@then("the address attributes are hidden")
def address_attributes_hidden(admin_logged_in_page: Page):
    expect(admin_logged_in_page.get_by_label("Address Attributes")).to_be_hidden()
    expect(admin_logged_in_page.get_by_text("Available respondent attributes")).to_be_hidden()


@then("the address attributes are shown")
def address_attributes_shown(admin_logged_in_page: Page):
    expect(admin_logged_in_page.get_by_label("Address Attributes")).to_be_visible()
    expect(admin_logged_in_page.get_by_text("Available respondent attributes")).to_be_visible()


@then(parsers.parse('the address attributes are "{attributes}"'))
def address_attributes_are(admin_logged_in_page: Page, attributes: str):
    expect(admin_logged_in_page.get_by_label("Address Attributes")).to_have_value(attributes)
