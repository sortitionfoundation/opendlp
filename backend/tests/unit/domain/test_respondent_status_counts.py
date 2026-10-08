"""ABOUTME: Unit tests for the respondent status helpers: the headline registration count and the labels.
ABOUTME: The dashboard, registration tab and respondents list all show these, so their rules live in one place."""

import pytest

from opendlp.domain.value_objects import RespondentStatus, headline_registration_count, respondent_status_labels


class TestHeadlineRegistrationCount:
    def test_counts_pool_selected_confirmed_and_withdrawn(self):
        counts = {
            RespondentStatus.POOL: 5,
            RespondentStatus.SELECTED: 3,
            RespondentStatus.CONFIRMED: 2,
            RespondentStatus.WITHDRAWN: 1,
        }

        assert headline_registration_count(counts) == 11

    def test_leaves_out_test_submissions_and_deleted_respondents(self):
        counts = {
            RespondentStatus.POOL: 4,
            RespondentStatus.TEST_SUBMISSION: 7,
            RespondentStatus.DELETED: 9,
        }

        assert headline_registration_count(counts) == 4

    def test_treats_a_missing_status_as_zero(self):
        assert headline_registration_count({RespondentStatus.WITHDRAWN: 2}) == 2

    def test_is_zero_with_no_respondents(self):
        assert headline_registration_count({}) == 0


@pytest.mark.parametrize("status", list(RespondentStatus))
class TestEveryRespondentStatusIsLabelled:
    """A status added later must not fall back to its raw enum value, which is
    untranslatable, and must appear as a filter on the respondents list."""

    def test_has_a_short_label(self, status):
        assert respondent_status_labels[status]
