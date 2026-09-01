# ABOUTME: Component tests for the dev-only service docs console after its script extraction
# ABOUTME: Pins the bundle tag, the JSON data block, and that every bound name is defined

import json
import re
from pathlib import Path

import pytest

from opendlp.entrypoints.blueprints.dev import SERVICE_RESPONSE_KEYS

SERVICE_DOCS_URL = "/backoffice/dev/service-docs"

TABS = [
    "respondents",
    "targets",
    "config",
    "selection",
    "assembly",
    "registration",
    "fields",
    "images",
    "documents",
    "emails",
    "dashboard",
]

# Where the extracted component lives. Read directly rather than through the built
# bundle: the bundle is a build artefact that may be stale, and what matters is that
# the source defines what the templates bind to.
COMPONENT_DIR = Path(__file__).resolve().parents[2] / "src/js/components/service-docs"

# Names that come from Alpine or the browser, not from our component.
ALPINE_BUILTINS = {"$event", "$el", "$refs", "$nextTick", "$watch", "$dispatch", "$store"}


@pytest.fixture
def page_html(logged_in_admin) -> str:
    response = logged_in_admin.get(SERVICE_DOCS_URL)
    assert response.status_code == 200
    return response.get_data(as_text=True)


@pytest.fixture
def every_tab_html(logged_in_admin) -> str:
    """Every tab's markup joined together.

    Only the active tab's partial is rendered, so a binding lives on exactly one tab -
    checking the default page alone would miss nine of the ten.
    """
    pages = []
    for tab in TABS:
        response = logged_in_admin.get(f"{SERVICE_DOCS_URL}?tab={tab}")
        assert response.status_code == 200, f"tab {tab} did not render"
        pages.append(response.get_data(as_text=True))
    return "\n".join(pages)


def _page_data(html: str) -> dict:
    match = re.search(
        r'<script type="application/json" id="service-docs-data"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match, "the service docs data block is missing"
    return json.loads(match.group(1))


def _component_source() -> str:
    """Every non-test module of the extracted component, concatenated."""
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(COMPONENT_DIR.glob("*.js"))
        if not path.name.endswith(".test.js")
    )


def _bound_calls(html: str) -> set[str]:
    """Method names called from an Alpine @click / @change expression."""
    calls = set()
    for expression in re.findall(r'@(?:click|change|input|submit)="([^"]+)"', html):
        calls.update(re.findall(r"\b([a-zA-Z_$][\w$]*)\s*\(", expression))
    return calls - ALPINE_BUILTINS


class TestTheBundle:
    def test_is_loaded(self, page_html: str):
        """The component comes from an entry point built out of src/js/backoffice/service-docs.js."""
        assert "backoffice/js/service-docs.js" in page_html

    def test_is_cache_busted_and_nonced(self, page_html: str):
        match = re.search(
            r'<script nonce="[^"]+"\s+src="[^"]*backoffice/js/service-docs\.js\?v=[^"]+"',
            page_html,
        )
        assert match, "the bundle must carry a CSP nonce and a static_hashes cache-buster"

    def test_registers_the_component_before_alpine_starts(self, page_html: str):
        """Its script sits after Alpine's in the document, which is only correct because
        Alpine's is deferred and the bundle's is not. Reverse either and the console
        silently loses every button."""
        alpine_tag = re.search(r"<script[^>]*alpine-csp\.js[^>]*>", page_html, re.DOTALL | re.IGNORECASE)
        bundle_tag = re.search(
            r"<script[^>]*backoffice/js/service-docs\.js[^>]*>", page_html, re.DOTALL | re.IGNORECASE
        )
        assert alpine_tag and bundle_tag
        assert "defer" in alpine_tag.group(0), "Alpine must stay deferred"
        assert "defer" not in bundle_tag.group(0), "the service docs bundle must not be deferred"

    @pytest.mark.parametrize("tab", TABS)
    def test_no_tab_carries_an_executable_inline_script(self, logged_in_admin, tab: str):
        """This page held the last inline script block in the repo - 722 lines of it.

        The JSON data block does not count: it has a type the browser will not run.
        """
        html = logged_in_admin.get(f"{SERVICE_DOCS_URL}?tab={tab}").get_data(as_text=True)

        inline_bodies = re.findall(
            r'<script(?![^>]*\ssrc=)(?![^>]*type="application/json")[^>]*>(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        assert [body for body in inline_bodies if body.strip()] == []


class TestTheDataBlock:
    def test_carries_the_execute_route(self, page_html: str):
        assert _page_data(page_html)["executeUrl"].endswith("/service-docs/execute")

    def test_carries_the_csrf_token_the_execute_route_requires(self, page_html: str):
        assert _page_data(page_html)["csrfToken"]

    def test_carries_the_response_key_for_every_service(self, page_html: str):
        """The map is dev.py's, so the page cannot drift from the handler table."""
        assert _page_data(page_html)["responseKeys"] == SERVICE_RESPONSE_KEYS


class TestTheBindings:
    def test_every_method_the_templates_call_is_defined(self, every_tab_html: str):
        """Alpine does not report an unknown method - the button just stops working.

        This is not a hypothetical: resetUpdateCsvConfig() was bound by the CSV config
        tab and defined nowhere, so that Reset button had been dead. Extracting the
        script is what made it visible, and this test is what keeps it visible.
        """
        source = _component_source()

        undefined = sorted(name for name in _bound_calls(every_tab_html) if f"{name}: function" not in source)

        assert not undefined, (
            f"Bound by a template but not defined in src/js/components/service-docs/: {', '.join(undefined)}"
        )

    def test_every_service_the_component_names_exists_on_the_server(self):
        """A slice calling executeService with an unknown name fails only when clicked."""
        called = set(re.findall(r'executeService\(\s*"([a-z_]+)"', _component_source()))

        assert called, "no executeService calls found - has the source moved?"
        assert called <= set(SERVICE_RESPONSE_KEYS)

    def test_every_service_has_a_button_somewhere(self):
        """The other direction: a handler nothing calls is a console page missing a control."""
        called = set(re.findall(r'executeService\(\s*"([a-z_]+)"', _component_source()))

        assert set(SERVICE_RESPONSE_KEYS) - called == set()


class TestTheTabs:
    @pytest.mark.parametrize("tab", TABS)
    def test_every_tab_renders(self, logged_in_admin, tab: str):
        """Each tab includes a different partial, so each is a separate chance to break."""
        response = logged_in_admin.get(f"{SERVICE_DOCS_URL}?tab={tab}")

        assert response.status_code == 200
        assert "backoffice/js/service-docs.js" in response.get_data(as_text=True)


class TestAccess:
    def test_a_non_admin_cannot_load_the_page(self, logged_in_user):
        assert logged_in_user.get(SERVICE_DOCS_URL).status_code in (302, 403, 404)
