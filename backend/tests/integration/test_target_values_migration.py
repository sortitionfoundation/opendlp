"""ABOUTME: Tests the data migration that rewrites stored TargetValue JSON.
ABOUTME: Inserts old-shape rows with raw SQL, since the repository writes the new shape."""

import json
import uuid

import pytest
from migrations.versions.bb9ef5dce9be_add_comment_and_source_url_to_target_ import REWRITE_TARGET_VALUES
from sqlalchemy import text

from opendlp.adapters.sql_repository import SqlAlchemyTargetCategoryRepository
from opendlp.domain.assembly import Assembly

# The shape an older version of the code wrote: a `description` key on every
# value, no `minmax_manual`, and a percentage on only some of them.
OLD_SHAPE_VALUES = [
    {
        "value": "Man",
        "min": 29,
        "max": 31,
        "min_flex": 0,
        "max_flex": -1,
        "percentage_target": 48.5,
        "description": "legacy",
        "value_id": "11111111-1111-1111-1111-111111111111",
    },
    {
        "value": "Woman",
        "min": 29,
        "max": 31,
        "min_flex": 0,
        "max_flex": -1,
        "percentage_target": None,
        "description": "legacy",
        "value_id": "22222222-2222-2222-2222-222222222222",
    },
    {
        "value": "Non-binary",
        "min": 1,
        "max": 2,
        "min_flex": 0,
        "max_flex": -1,
        "description": "legacy",
        "value_id": "33333333-3333-3333-3333-333333333333",
    },
]


@pytest.fixture
def assembly(postgres_session):
    item = Assembly(title="Migration test", question="?", number_to_select=60)
    postgres_session.add(item)
    postgres_session.commit()
    return item


def _insert_category(session, assembly_id, name, values):
    category_id = uuid.uuid4()
    session.execute(
        text(
            """
            INSERT INTO target_categories (id, assembly_id, name, comment, source_url, sort_order,
                                           "values", created_at, updated_at)
            VALUES (:id, :assembly_id, :name, '', '', 0, :values, now(), now())
            """
        ),
        {"id": category_id, "assembly_id": assembly_id, "name": name, "values": json.dumps(values)},
    )
    return category_id


def _read_values(session, category_id):
    row = session.execute(
        text('SELECT "values" FROM target_categories WHERE id = :id'), {"id": category_id}
    ).scalar_one()
    return json.loads(row) if isinstance(row, str) else row


class TestRewriteTargetValues:
    def test_strips_description_and_sets_minmax_manual_where_a_percentage_exists(self, postgres_session, assembly):
        category_id = _insert_category(postgres_session, assembly.id, "Gender", OLD_SHAPE_VALUES)

        postgres_session.execute(text(REWRITE_TARGET_VALUES))

        values = _read_values(postgres_session, category_id)
        assert all("description" not in v for v in values)
        # Only the value that already carried a number is marked manual. A JSON
        # null and a missing key must both be left alone, so they decode to the
        # dataclass default of False.
        assert values[0]["minmax_manual"] is True
        assert "minmax_manual" not in values[1]
        assert "minmax_manual" not in values[2]

    def test_preserves_the_order_of_values(self, postgres_session, assembly):
        """Order within a category is the display order."""
        category_id = _insert_category(postgres_session, assembly.id, "Gender", OLD_SHAPE_VALUES)

        postgres_session.execute(text(REWRITE_TARGET_VALUES))

        values = _read_values(postgres_session, category_id)
        assert [v["value"] for v in values] == ["Man", "Woman", "Non-binary"]

    def test_leaves_an_empty_category_valid(self, postgres_session, assembly):
        category_id = _insert_category(postgres_session, assembly.id, "Empty", [])

        postgres_session.execute(text(REWRITE_TARGET_VALUES))

        assert _read_values(postgres_session, category_id) == []

    def test_is_idempotent(self, postgres_session, assembly):
        category_id = _insert_category(postgres_session, assembly.id, "Gender", OLD_SHAPE_VALUES)

        postgres_session.execute(text(REWRITE_TARGET_VALUES))
        first = _read_values(postgres_session, category_id)
        postgres_session.execute(text(REWRITE_TARGET_VALUES))

        assert _read_values(postgres_session, category_id) == first

    def test_rewritten_rows_load_through_the_repository(self, postgres_session, assembly):
        category_id = _insert_category(postgres_session, assembly.id, "Gender", OLD_SHAPE_VALUES)
        postgres_session.execute(text(REWRITE_TARGET_VALUES))
        postgres_session.commit()
        postgres_session.expunge_all()

        category = SqlAlchemyTargetCategoryRepository(postgres_session).get(category_id)

        assert [v.value for v in category.values] == ["Man", "Woman", "Non-binary"]
        assert category.values[0].minmax_manual is True
        assert category.values[1].minmax_manual is False
