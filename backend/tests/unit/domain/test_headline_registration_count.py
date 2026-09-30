"""ABOUTME: Unit tests for headline_registration_count, the "how many people registered" figure.
ABOUTME: The dashboard and the registration tab both show it, so its rule lives in one place."""

from opendlp.domain.value_objects import RespondentStatus, headline_registration_count


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
