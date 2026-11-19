"""ABOUTME: Unit tests for which registration page the project details page shows, and what its link says.
ABOUTME: Covers the order of preference - published, in test, oldest - and the three link texts."""

import uuid

import pytest
from flask import Flask

from opendlp.domain.registration_page import RegistrationPage, RegistrationPageStatus
from opendlp.entrypoints.registration_link_card import featured_registration_page, registration_tab_link_text

ASSEMBLY_ID = uuid.uuid4()


def _page(name: str, status: RegistrationPageStatus) -> RegistrationPage:
    page = RegistrationPage(assembly_id=ASSEMBLY_ID, name=name, url_slug=name)
    page.status = status
    return page


class TestFeaturedRegistrationPage:
    def test_no_pages_means_no_page(self):
        assert featured_registration_page([]) is None

    def test_a_lone_page_is_shown_whatever_its_status(self):
        closed = _page("closed", RegistrationPageStatus.CLOSED)

        assert featured_registration_page([closed]) is closed

    def test_a_published_page_comes_before_older_ones(self):
        """A project with an old closed page and a live one must not show the dead link."""
        pages = [
            _page("closed", RegistrationPageStatus.CLOSED),
            _page("test", RegistrationPageStatus.TEST),
            _page("live", RegistrationPageStatus.PUBLISHED),
        ]

        assert featured_registration_page(pages).name == "live"

    def test_the_first_of_several_published_pages_is_shown(self):
        pages = [
            _page("live-en", RegistrationPageStatus.PUBLISHED),
            _page("live-es", RegistrationPageStatus.PUBLISHED),
        ]

        assert featured_registration_page(pages).name == "live-en"

    def test_a_page_in_test_comes_before_a_closed_one(self):
        pages = [_page("closed", RegistrationPageStatus.CLOSED), _page("test", RegistrationPageStatus.TEST)]

        assert featured_registration_page(pages).name == "test"

    def test_with_only_closed_pages_the_oldest_is_shown(self):
        pages = [_page("first", RegistrationPageStatus.CLOSED), _page("second", RegistrationPageStatus.CLOSED)]

        assert featured_registration_page(pages).name == "first"


class TestRegistrationTabLinkText:
    @pytest.fixture(autouse=True)
    def request_context(self):
        app = Flask(__name__)
        with app.test_request_context("/"):
            yield

    @pytest.mark.parametrize(
        ("count", "text"),
        [(0, "Create"), (1, "See details"), (2, "See all (2)"), (3, "See all (3)")],
    )
    def test_the_link_says_what_following_it_does(self, count: int, text: str):
        assert registration_tab_link_text(count) == text
