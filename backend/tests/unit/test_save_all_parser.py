"""ABOUTME: Unit tests for the bulk targets edit form parser
ABOUTME: Covers field-name parsing, numeric cells, new values and malformed input"""

import uuid

from opendlp.entrypoints.save_all_parser import parse_save_all_targets

CATEGORY_ID = uuid.uuid4()
_NAME_REQUIRED = "Every target needs a name"
VALUE_ID = uuid.uuid4()


def _form(**extra):
    data = {
        "csrf_token": "irrelevant",
        f"cat[{CATEGORY_ID}][name]": "Gender",
        f"cat[{CATEGORY_ID}][comment]": "from the census",
        f"cat[{CATEGORY_ID}][source_url]": "https://www.ons.gov.uk/dataset",
    }
    data.update(extra)
    return data


class TestParseSaveAllTargets:
    def test_parses_category_fields(self):
        edits, errors = parse_save_all_targets(_form())

        assert errors == []
        assert len(edits) == 1
        assert edits[0].category_id == CATEGORY_ID
        assert edits[0].name == "Gender"
        assert edits[0].comment == "from the census"
        assert edits[0].source_url == "https://www.ons.gov.uk/dataset"

    def test_parses_value_fields(self):
        edits, errors = parse_save_all_targets(
            _form(**{
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][value]": "Male",
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][percentage]": "48.5",
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][min]": "10",
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][max]": "15",
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][comment]": "boosted",
            })
        )

        assert errors == []
        value = edits[0].values[0]
        assert value.value_id == VALUE_ID
        assert value.value == "Male"
        assert value.percentage == 48.5
        assert (value.min, value.max) == (10, 15)
        assert value.comment == "boosted"

    def test_a_new_value_has_no_value_id(self):
        edits, errors = parse_save_all_targets(
            _form(**{
                f"cat[{CATEGORY_ID}][values][new-1][value]": "Non-binary",
                f"cat[{CATEGORY_ID}][values][new-1][percentage]": "2",
            })
        )

        assert errors == []
        assert edits[0].values[0].value_id is None
        assert edits[0].values[0].value == "Non-binary"

    def test_empty_numeric_cells_become_none(self):
        """An empty cell means 'not submitted', not zero."""
        edits, errors = parse_save_all_targets(
            _form(**{
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][value]": "Male",
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][percentage]": "",
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][min]": "",
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][max]": "",
            })
        )

        assert errors == []
        value = edits[0].values[0]
        assert value.percentage is None
        assert value.min is None
        assert value.max is None

    def test_a_non_numeric_cell_is_reported_not_raised(self):
        edits, errors = parse_save_all_targets(
            _form(**{
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][value]": "Male",
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][min]": "ten",
            })
        )

        assert len(errors) == 1
        assert "ten" in errors[0].message
        assert (errors[0].category_form_id, errors[0].value_form_id, errors[0].field) == (
            str(CATEGORY_ID),
            str(VALUE_ID),
            "min",
        )
        assert edits[0].values[0].min is None

    def test_a_value_with_no_name_is_reported(self):
        _edits, errors = parse_save_all_targets(_form(**{f"cat[{CATEGORY_ID}][values][{VALUE_ID}][value]": "   "}))

        assert len(errors) == 1

    def test_unrecognised_field_names_are_ignored(self):
        """The form also carries the CSRF token and whatever else the page needs."""
        edits, errors = parse_save_all_targets(_form(**{"something_else": "x", f"cat[{CATEGORY_ID}][unknown]": "y"}))

        assert errors == []
        assert len(edits) == 1

    def test_an_empty_form_produces_no_edits(self):
        edits, errors = parse_save_all_targets({"csrf_token": "irrelevant"})

        assert edits == []
        assert errors == []


class TestDeletionAndRelinking:
    def test_a_value_marked_deleted_is_flagged(self):
        edits, errors = parse_save_all_targets(
            _form(**{
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][value]": "Male",
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][deleted]": "true",
            })
        )

        assert errors == []
        assert edits[0].values[0].deleted is True

    def test_a_value_not_marked_deleted_is_not_flagged(self):
        edits, _errors = parse_save_all_targets(
            _form(**{
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][value]": "Male",
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][deleted]": "false",
            })
        )

        assert edits[0].values[0].deleted is False

    def test_a_deleted_value_needs_no_name(self):
        """The name field of a row on its way out is nobody's business."""
        edits, errors = parse_save_all_targets(
            _form(**{
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][value]": "",
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][deleted]": "true",
            })
        )

        assert errors == []
        assert edits[0].values[0].deleted is True

    def test_a_category_marked_deleted_is_flagged(self):
        edits, errors = parse_save_all_targets(_form(**{f"cat[{CATEGORY_ID}][deleted]": "true"}))

        assert errors == []
        assert edits[0].deleted is True

    def test_a_deleted_category_carries_no_value_edits(self):
        """Its values go with it, so validating or applying them is pointless."""
        edits, errors = parse_save_all_targets(
            _form(**{
                f"cat[{CATEGORY_ID}][deleted]": "true",
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][value]": "",
            })
        )

        assert errors == []
        assert edits[0].values == []

    def test_a_relink_request_is_flagged(self):
        edits, _errors = parse_save_all_targets(
            _form(**{
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][value]": "Male",
                f"cat[{CATEGORY_ID}][values][{VALUE_ID}][relink]": "true",
            })
        )

        assert edits[0].values[0].relink is True

    def test_sort_order_is_parsed_as_a_number(self):
        edits, errors = parse_save_all_targets(_form(**{f"cat[{CATEGORY_ID}][sort_order]": "30"}))

        assert errors == []
        assert edits[0].sort_order == 30

    def test_a_missing_sort_order_means_leave_it_alone(self):
        edits, _errors = parse_save_all_targets(_form())

        assert edits[0].sort_order is None


class TestNewCategories:
    def test_a_new_category_has_no_category_id(self):
        edits, errors = parse_save_all_targets({
            "cat[new-1][name]": "Age",
            "cat[new-1][sort_order]": "30",
            "cat[new-1][values][new-1][value]": "16-29",
            "cat[new-1][values][new-1][percentage]": "25",
        })

        assert errors == []
        assert len(edits) == 1
        assert edits[0].category_id is None
        assert edits[0].name == "Age"
        assert edits[0].sort_order == 30
        assert edits[0].values[0].value_id is None
        assert edits[0].values[0].value == "16-29"

    def test_a_category_with_no_name_is_reported(self):
        _edits, errors = parse_save_all_targets({f"cat[{CATEGORY_ID}][name]": "   "})

        assert [e.message for e in errors] == [_NAME_REQUIRED]
        assert (errors[0].category_form_id, errors[0].field) == (str(CATEGORY_ID), "name")

    def test_a_nameless_category_still_produces_an_edit(self):
        """The error stops the save; the edit is what puts the row back on the page to fix."""
        edits, errors = parse_save_all_targets({f"cat[{CATEGORY_ID}][name]": ""})

        assert errors
        assert len(edits) == 1
        assert edits[0].name == ""

    def test_a_deleted_category_still_needs_no_name(self):
        edits, errors = parse_save_all_targets({
            f"cat[{CATEGORY_ID}][name]": "",
            f"cat[{CATEGORY_ID}][deleted]": "true",
        })

        assert errors == []
        assert edits[0].deleted is True
