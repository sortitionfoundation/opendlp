"""ABOUTME: Component tests for the info cards a Google Sheets assembly shows in place of its editors
ABOUTME: Targets, respondents, registration questions and target data sources all point at the spreadsheet"""

from datetime import UTC, datetime, timedelta

import pytest

from opendlp.service_layer.assembly_service import add_assembly_gsheet, create_assembly
from tests.fakes import FakeUnitOfWork


@pytest.fixture
def gsheet_assembly(fake_store, admin_user):
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Assembly on a spreadsheet",
            created_by_user_id=admin_user.id,
            question="What should we do?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            number_to_select=22,
        )
        detached = assembly.create_detached_copy()
    with FakeUnitOfWork(store=fake_store) as uow:
        add_assembly_gsheet(
            uow=uow,
            assembly_id=detached.id,
            user_id=admin_user.id,
            url="https://docs.google.com/spreadsheets/d/1234567890abcdef/edit",
            team="uk",
            select_registrants_tab="TestRespondents",
            select_targets_tab="TestCategories",
            id_column="test_id_column",
        )
    return detached


@pytest.mark.parametrize(
    ("page", "heading", "detail"),
    [
        ("targets", "Targets are configured in Google Sheets", "TestCategories"),
        ("respondents", "Respondents are configured in Google Sheets", "TestRespondents"),
        ("respondent-schema", "Fields are defined by your Google Sheets spreadsheet", "TestRespondents"),
        ("target-sources", "", "Fields are defined by your Google Sheets spreadsheet — manage them there."),
    ],
)
def test_each_page_points_at_the_spreadsheet_in_an_info_card(logged_in_admin, gsheet_assembly, page, heading, detail):
    body = logged_in_admin.get(f"/backoffice/assembly/{gsheet_assembly.id}/{page}").get_data(as_text=True)

    card = body[body.index('<section class="mb-8">') :]
    card = card[: card.index("</section>")]
    assert "border: 1px solid var(--color-borders-dividers)" in card
    assert "<svg" in card
    if heading:
        assert f">{heading}</h2>" in card
    assert detail in card
