"""ABOUTME: What the Registration link card on the project details page shows
ABOUTME: One registration page's links, chosen from however many the project has, and the card's link to the rest"""

from opendlp.domain.registration_page import RegistrationPage, RegistrationPageStatus
from opendlp.translations import gettext as _

# A page people can register on comes before one still being tested, and
# either before one that has closed.
_PREFERENCE = (RegistrationPageStatus.PUBLISHED, RegistrationPageStatus.TEST)


def featured_registration_page(pages: list[RegistrationPage]) -> RegistrationPage | None:
    """The page whose links the card shows: the first published, else the first in test, else the oldest.

    `pages` is in the order they were created. A project with an old closed
    page and a live one shows the live one's link, not the dead one's.
    """
    for status in _PREFERENCE:
        for page in pages:
            if page.status == status:
                return page
    return pages[0] if pages else None


def registration_tab_link_text(page_count: int) -> str:
    """What the card's link to the Registration tab says, which depends on how many pages there are."""
    if page_count == 0:
        return _("Create")
    if page_count == 1:
        return _("See details")
    return _("See all (%(count)s)", count=page_count)
