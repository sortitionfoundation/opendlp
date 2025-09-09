from playwright.sync_api import Page, expect


def check_follow_link(page: Page, link_name: str, link_url: str) -> None:
    """
    This allows us to check links which open in a new tab - eg with `target="_blank"`
    - Find a link in the page,
    - check following it leads to an expected URL,
    - have the main page object actually go to that URL.
    """
    link = page.get_by_role("link", name=link_name)
    expect(link).to_be_visible()
    # the link is opened in a new tab - first we check that the new
    # page has the expected URL
    with page.context.expect_page() as followed_page:
        link.click()
    expect(followed_page.value).to_have_url(link_url)
    # now we've confirmed the NEW page has the expected URL
    # we manually navigate the original page to that URL, so that
    # we are ready for the "then" step to check the contents of the page
    page.goto(link_url)
