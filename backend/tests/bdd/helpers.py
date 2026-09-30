from playwright.sync_api import Page, expect


def wait_for_page_with_text(page: Page, text: str) -> None:
    """
    Sometimes we want to look in the database directly. But maybe the tests are fast and
    the web server hasn't finished saving the object yet.  To keep the tests deterministic
    we will wait for text to appear that is on the landing page after the web server
    has saved any changes.
    We ask playwright to click on the text, which requires the text to be visible.
    Due to it being a click, we should choose text that doesn't do anything when clicked on.
    """
    page.get_by_text(text).click()


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
    followed_page.value.close()
    # now we've confirmed the NEW page has the expected URL
    # we manually navigate the original page to that URL, so that
    # we are ready for the "then" step to check the contents of the page
    page.goto(link_url)


def assert_step_dialog_dimmed(page: Page, host_selector: str) -> None:
    """
    A fragment dialog opened over a registration step's takeover dialog must grey
    the step out, so it reads as out of reach. Checks that, at a point on the step's
    panel clear of the fragment dialog, the topmost element is the fragment
    dialog's backdrop - not the step's own panel.
    """
    expect(page.locator(f"{host_selector} [role='dialog']")).to_be_visible()
    step_panel = page.locator(".dialog-panel--takeover").bounding_box()
    assert step_panel is not None
    # The top-left corner of the step's panel: its header, well clear of the
    # narrower fragment dialog centred over it.
    x, y = step_panel["x"] + 10, step_panel["y"] + 10
    # The step dialog is inert while the fragment dialog is open, and hit testing
    # passes straight through inert elements - so lift it for the probe, or the
    # backdrop would be found even when painted underneath the step's panel.
    covered_by_host_backdrop = page.evaluate(
        """([x, y, hostSelector]) => {
            const step = document.querySelector(".dialog-positioner:has(.dialog-panel--takeover)");
            const wasInert = step.inert;
            step.inert = false;
            const top = document.elementFromPoint(x, y);
            step.inert = wasInert;
            return !!top && top.matches(".dialog-backdrop") && !!top.closest(hostSelector);
        }""",
        [x, y, host_selector],
    )
    assert covered_by_host_backdrop, "the step dialog behind the fragment dialog is not dimmed"
