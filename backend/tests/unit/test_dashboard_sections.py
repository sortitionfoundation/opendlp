"""ABOUTME: Unit tests for _build_dashboard_sections, the report -> pie-card view-model mapping.
ABOUTME: Pure function (no uow), so it is exercised here directly rather than through the route."""

from opendlp.entrypoints.blueprints.backoffice import _build_dashboard_sections, _build_dashboard_tables
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


def _row(
    value: str,
    pool_count: int,
    shortfall: int,
    *,
    target_pct: float = 50.0,
    selected_count: int = 0,
    confirmed_count: int = 0,
) -> CategoryValueRow:
    return CategoryValueRow(
        value=value,
        target_min=10,
        target_max=12,
        target_pct=target_pct,
        pool_count=pool_count,
        available_count=pool_count,
        selected_count=selected_count,
        confirmed_count=confirmed_count,
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


def test_selected_and_confirmed_cards_are_skeletons_when_there_is_none_yet():
    # _gender_rows has zero selected/confirmed, so those datasets stay skeletons.
    cards = _build_dashboard_sections(_report(DashboardCategory(name="Gender", rows=_gender_rows())))[0]["cards"]

    for card in (cards[2], cards[3]):
        assert card["segments"] is None
        assert card["message"]  # non-empty skeleton message


def test_selected_and_confirmed_cards_populate_from_real_counts():
    rows = [
        _row("Male", pool_count=8, shortfall=0, selected_count=3, confirmed_count=1),
        _row("Female", pool_count=14, shortfall=0, selected_count=1, confirmed_count=1),
    ]
    cards = _build_dashboard_sections(_report(DashboardCategory(name="Gender", rows=rows)))[0]["cards"]

    assert cards[2]["segments"] == [{"label": "Male", "count": 3}, {"label": "Female", "count": 1}]
    assert cards[3]["segments"] == [{"label": "Male", "count": 1}, {"label": "Female", "count": 1}]


def test_respondents_card_is_a_skeleton_when_the_pool_is_empty():
    rows = [_row("Male", pool_count=0, shortfall=10)]
    cards = _build_dashboard_sections(_report(DashboardCategory(name="Gender", rows=rows)))[0]["cards"]

    # Target still populates from the band; Respondents has no data yet.
    assert cards[0]["segments"] == [{"label": "Male", "count": 11}]
    assert cards[1]["segments"] is None
    assert cards[1]["message"]


class TestBuildDashboardTables:
    def test_one_table_per_category_with_a_row_per_value(self):
        tables = _build_dashboard_tables(_report(DashboardCategory(name="Gender", rows=_gender_rows())))

        assert len(tables) == 1
        assert tables[0]["name"] == "Gender"
        assert [r["value"] for r in tables[0]["rows"]] == ["Male", "Female"]

    def test_target_uses_the_service_pct_and_the_band_midpoint(self):
        rows = _build_dashboard_tables(_report(DashboardCategory(name="Gender", rows=_gender_rows())))[0]["rows"]
        male = rows[0]

        # target_pct comes straight from the row; the count is the band midpoint (10+12)/2
        assert male["target_pct"] == "50.0"
        assert male["target_count"] == 11

    def test_respondent_percentages_are_each_value_share_of_the_pool(self):
        male, female = _build_dashboard_tables(_report(DashboardCategory(name="Gender", rows=_gender_rows())))[0][
            "rows"
        ]

        assert male["respondents_count"] == 8
        assert male["respondents_pct"] == "36.4"  # 8 / 22
        assert female["respondents_pct"] == "63.6"  # 14 / 22

    def test_selected_and_confirmed_come_from_the_row_counts(self):
        rows_in = [
            _row("Male", pool_count=8, shortfall=0, selected_count=3, confirmed_count=1),
            _row("Female", pool_count=14, shortfall=0, selected_count=1, confirmed_count=1),
        ]
        male = _build_dashboard_tables(_report(DashboardCategory(name="Gender", rows=rows_in)))[0]["rows"][0]

        assert male["selected_count"] == 3
        assert male["selected_pct"] == "75.0"  # 3 of 4 selected in the category
        assert male["confirmed_count"] == 1
        assert male["confirmed_pct"] == "50.0"  # 1 of 2 confirmed

    def test_empty_datasets_render_as_zero_without_dividing_by_zero(self):
        rows = [_row("Male", pool_count=0, shortfall=10)]
        row = _build_dashboard_tables(_report(DashboardCategory(name="Gender", rows=rows)))[0]["rows"][0]

        assert row["respondents_pct"] == "0.0"
        assert row["selected_pct"] == "0.0"
        assert row["confirmed_pct"] == "0.0"
