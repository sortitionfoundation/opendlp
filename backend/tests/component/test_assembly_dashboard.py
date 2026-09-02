"""ABOUTME: Component tests for the assembly results dashboard page and pie chart atom (ticket 886).
ABOUTME: Covers the page render, the FF_RESULTS_DASHBOARD tab gating, and the atom's two states."""

import os
import re

import pytest
from flask import render_template_string

from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.value_objects import RespondentStatus
from opendlp.feature_flags import reload_flags
from tests.fakes import FakeUnitOfWork


def _dashboard_url(assembly) -> str:
    return f"/backoffice/assembly/{assembly.id}/dashboard"


def _members_url(assembly) -> str:
    return f"/backoffice/assembly/{assembly.id}/members"


def _indicator_values(html: str) -> list[str]:
    """The bold numbers in the "Number to select / Number of registrations" row."""
    return re.findall(r'font-weight: 700;">(\d+)</span>', html)


@pytest.fixture
def assembly_with_targets(fake_store, existing_assembly):
    """One Gender category, so the page has a section to render."""
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.target_categories.add(
            TargetCategory(
                assembly_id=existing_assembly.id,
                name="Gender",
                values=[
                    TargetValue(value="Male", min=10, max=12),
                    TargetValue(value="Female", min=10, max=12),
                ],
            )
        )
        uow.commit()
    return existing_assembly


@pytest.fixture
def assembly_with_respondents(fake_store, existing_assembly):
    """25 registrations, plus a test submission and a deletion that do not count."""
    with FakeUnitOfWork(store=fake_store) as uow:
        statuses = (
            [RespondentStatus.POOL] * 20
            + [RespondentStatus.SELECTED] * 3
            + [RespondentStatus.CONFIRMED] * 1
            + [RespondentStatus.WITHDRAWN] * 1
            + [RespondentStatus.TEST_SUBMISSION] * 4
            + [RespondentStatus.DELETED] * 2
        )
        for index, status in enumerate(statuses):
            uow.respondents.add(
                Respondent(
                    assembly_id=existing_assembly.id,
                    external_id=f"R{index:03d}",
                    selection_status=status,
                )
            )
        uow.commit()
    return existing_assembly


@pytest.fixture
def results_dashboard_on():
    """Turn FF_RESULTS_DASHBOARD on for the duration of a test, then restore."""
    os.environ["FF_RESULTS_DASHBOARD"] = "true"
    reload_flags()
    yield
    os.environ.pop("FF_RESULTS_DASHBOARD", None)
    reload_flags()


class TestTheDashboardPage:
    def test_renders_indicators_and_sections(self, logged_in_admin, assembly_with_targets):
        html = logged_in_admin.get(_dashboard_url(assembly_with_targets)).get_data(as_text=True)

        assert "Number to select:" in html
        assert "Number of registrations:" in html
        # one section per target category
        assert ">Gender<" in html

    def test_an_assembly_with_no_targets_renders_no_sections(self, logged_in_admin, existing_assembly):
        html = logged_in_admin.get(_dashboard_url(existing_assembly)).get_data(as_text=True)

        assert "Number to select:" in html
        assert "conic-gradient(" not in html

    def test_the_registration_count_excludes_test_and_deleted_respondents(
        self,
        logged_in_admin,
        assembly_with_respondents,
    ):
        html = logged_in_admin.get(_dashboard_url(assembly_with_respondents)).get_data(as_text=True)

        assert _indicator_values(html) == ["0", "25"]

    def test_an_assembly_with_no_respondents_shows_no_registrations(self, logged_in_admin, existing_assembly):
        html = logged_in_admin.get(_dashboard_url(existing_assembly)).get_data(as_text=True)

        assert _indicator_values(html) == ["0", "0"]

    def test_target_pie_is_populated_and_later_datasets_are_skeletons(self, logged_in_admin, assembly_with_targets):
        html = logged_in_admin.get(_dashboard_url(assembly_with_targets)).get_data(as_text=True)

        # Target renders a real pie
        assert "conic-gradient(" in html
        # Selected / Confirmed render their skeleton messages
        assert "Shows selected data once selection has happened." in html
        assert "Shows confirmed data once at least one selected respondent is confirmed." in html

    def test_route_is_reachable_even_when_the_flag_is_off(self, logged_in_admin, existing_assembly):
        # The flag only hides the tab; the route stays reachable by URL.
        assert logged_in_admin.get(_dashboard_url(existing_assembly)).status_code == 200


class TestTheTabGating:
    def test_tab_is_hidden_by_default(self, logged_in_admin, existing_assembly):
        html = logged_in_admin.get(_members_url(existing_assembly)).get_data(as_text=True)
        assert _dashboard_url(existing_assembly) not in html

    def test_tab_is_shown_when_the_flag_is_on(self, logged_in_admin, existing_assembly, results_dashboard_on):
        html = logged_in_admin.get(_members_url(existing_assembly)).get_data(as_text=True)
        assert _dashboard_url(existing_assembly) in html


class TestThePieChartAtom:
    _IMPORT = '{% from "backoffice/components/pie_chart_card.html" import pie_chart_card %}'

    def _render(self, app, body: str, **ctx: object) -> str:
        with app.test_request_context():
            return render_template_string(self._IMPORT + body, **ctx)

    def test_populated_state_draws_a_pie_with_legends(self, app):
        html = self._render(
            app,
            "{{ pie_chart_card('Gender', segments=segments, title_tag='h4') }}",
            segments=[
                {"label": "Male", "count": 10},
                {"label": "Female", "count": 9},
                {"label": "Non-binary", "count": 1},
            ],
        )
        assert 'role="img"' in html
        assert "conic-gradient(" in html
        # percentages are computed from the counts (10/20 = 50%)
        assert "Male 50% (10)" in html
        # title_tag is honoured
        assert "<h4" in html

    def test_skeleton_state_shows_the_message_and_no_chart_role(self, app):
        html = self._render(
            app,
            "{{ pie_chart_card('Respondents', message=message) }}",
            message="Shows respondent data once registration starts.",
        )
        assert "Shows respondent data once registration starts." in html
        assert 'aria-hidden="true"' in html
        assert 'role="img"' not in html
