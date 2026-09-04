"""ABOUTME: Unit tests for _build_dashboard_sections, the report -> pie-card view-model mapping.
ABOUTME: Pure function (no uow), so it is exercised here directly rather than through the route."""

from opendlp.entrypoints.blueprints.backoffice import _build_dashboard_sections
from opendlp.service_layer.dashboard_stats import CategoryValueRow, DashboardCategory, DashboardReport


def _report(*categories: DashboardCategory) -> DashboardReport:
    return DashboardReport(
        assembly_id="a-1",
        assembly_title="A",
        number_to_select=25,
        pool_size=0,
        categories=list(categories),
        unmet_targets=[],
    )


def _row(value: str, pool_count: int, shortfall: int) -> CategoryValueRow:
    return CategoryValueRow(
        value=value,
        target_min=10,
        target_max=12,
        target_pct=50.0,
        pool_count=pool_count,
        available_count=pool_count,
        selected_count=0,
        confirmed_count=0,
        shortfall=shortfall,
        meetable=shortfall == 0,
    )


def _gender_rows() -> list[CategoryValueRow]:
    return [_row("Male", pool_count=8, shortfall=2), _row("Female", pool_count=14, shortfall=0)]


def test_one_section_per_category_with_four_dataset_cards():
    sections = _build_dashboard_sections(_report(DashboardCategory(name="Gender", rows=_gender_rows())))

    assert len(sections) == 1
    assert sections[0]["name"] == "Gender"
    cards = sections[0]["cards"]
    assert len(cards) == 4


def test_target_card_segments_use_band_midpoints():
    cards = _build_dashboard_sections(_report(DashboardCategory(name="Gender", rows=_gender_rows())))[0]["cards"]

    # (10 + 12) / 2 -> 11 for both values
    assert cards[0]["segments"] == [
        {"label": "Male", "count": 11},
        {"label": "Female", "count": 11},
    ]


def test_respondents_card_segments_use_pool_counts():
    cards = _build_dashboard_sections(_report(DashboardCategory(name="Gender", rows=_gender_rows())))[0]["cards"]

    assert cards[1]["segments"] == [
        {"label": "Male", "count": 8},
        {"label": "Female", "count": 14},
    ]


def test_selected_and_confirmed_cards_are_skeletons_with_a_message():
    cards = _build_dashboard_sections(_report(DashboardCategory(name="Gender", rows=_gender_rows())))[0]["cards"]

    for card in (cards[2], cards[3]):
        assert card["segments"] is None
        assert card["message"]  # non-empty skeleton message


def test_respondents_card_is_a_skeleton_when_the_pool_is_empty():
    rows = [_row("Male", pool_count=0, shortfall=10)]
    cards = _build_dashboard_sections(_report(DashboardCategory(name="Gender", rows=rows)))[0]["cards"]

    # Target still populates from the band; Respondents has no data yet.
    assert cards[0]["segments"] == [{"label": "Male", "count": 11}]
    assert cards[1]["segments"] is None
    assert cards[1]["message"]
