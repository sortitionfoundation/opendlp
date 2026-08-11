# ABOUTME: Component tests for the dev-only frontend patterns reference page
# ABOUTME: Pins that its JavaScript is a built bundle, not the inline block it used to carry

import re

import pytest

PATTERNS_URL = "/backoffice/dev/patterns"

# Alpine bindings the extracted components have to keep satisfying. If a property
# or method is renamed in src/js/ and not here, the page silently renders nothing
# where the binding was - Alpine does not report an unknown property.
BOUND_NAMES = [
    "patternsController()",
    "fileUploadDemo()",
    "toast.show",
    "toast.message",
    "copyUrlSelectCode()",
    "copyInlineSelectCode()",
    "copyFileUploadTemplateCode()",
    "copyFileUploadRouteCode()",
    "copyProgressBarCode()",
    "copyPaginationTemplateCode()",
    "copyPaginationRouteCode()",
    "copyScrollPreserveCode()",
    "copyPreserveScrollCode()",
    "copyScrollDirectiveCode()",
    "copyNavigateScrollCode()",
    "demoAssemblyId",
]


TABS = [
    "dropdown",
    "form",
    "ajax",
    "file-upload",
    "progress",
    "pagination",
    "scroll",
    "focus",
    "floating-alerts",
    "custom",
    "stepper",
]


@pytest.fixture
def patterns_html(logged_in_admin) -> str:
    response = logged_in_admin.get(PATTERNS_URL)
    assert response.status_code == 200
    return response.get_data(as_text=True)


@pytest.fixture
def all_tabs_html(logged_in_admin) -> str:
    """Every tab's markup joined together.

    Only the active tab's partial is rendered, so a binding lives on exactly one
    tab - checking the default page alone would miss nine of the eleven.
    """
    pages = []
    for tab in TABS:
        response = logged_in_admin.get(f"{PATTERNS_URL}?tab={tab}")
        assert response.status_code == 200, f"tab {tab} did not render"
        pages.append(response.get_data(as_text=True))
    return "\n".join(pages)


class TestPatternsPageAccess:
    def test_admin_can_load_the_page(self, logged_in_admin):
        assert logged_in_admin.get(PATTERNS_URL).status_code == 200

    def test_a_non_admin_cannot(self, logged_in_user):
        assert logged_in_user.get(PATTERNS_URL).status_code in (302, 403, 404)


class TestPatternsPageScripts:
    def test_loads_the_patterns_bundle(self, patterns_html: str):
        """The components come from an entry point built out of src/js/backoffice/patterns.js."""
        assert "backoffice/js/patterns.js" in patterns_html

    def test_the_bundle_is_cache_busted_and_nonced(self, patterns_html: str):
        match = re.search(r'<script nonce="[^"]+"\s+src="[^"]*backoffice/js/patterns\.js\?v=[^"]+"', patterns_html)
        assert match, "the patterns bundle must carry a CSP nonce and a static_hashes cache-buster"

    def test_registers_its_components_before_alpine_starts(self, patterns_html: str):
        """The bundle must run before Alpine, or its alpine:init listener is registered too late.

        The bundle's <script> sits in the head block, *after* Alpine's tag in the
        document. That is still correct, but only because Alpine's tag is deferred
        and the bundle's is not: a non-deferred script runs during parsing, a
        deferred one only once parsing finishes. Drop the defer, or add one to the
        bundle, and the components silently fail to register.
        """
        alpine_tag = re.search(r"<script[^>]*alpine-csp\.js[^>]*>", patterns_html, re.DOTALL | re.IGNORECASE)
        bundle_tag = re.search(
            r"<script[^>]*backoffice/js/patterns\.js[^>]*>", patterns_html, re.DOTALL | re.IGNORECASE
        )
        assert alpine_tag and bundle_tag
        assert "defer" in alpine_tag.group(0), "Alpine must stay deferred"
        assert "defer" not in bundle_tag.group(0), "the patterns bundle must not be deferred"

    def test_carries_no_inline_script_body_at_all(self, patterns_html: str):
        """The page used to define 284 lines of Alpine components in an inline block.

        It must not again: every <script> on the page is now a src= reference. Note
        this cannot be checked by grepping for "Alpine.data(" - the page documents
        that call in its prose, which is rather the point of it.
        """
        inline_bodies = re.findall(
            r"<script(?![^>]*\ssrc=)[^>]*>(.*?)</script>", patterns_html, re.DOTALL | re.IGNORECASE
        )
        assert [body for body in inline_bodies if body.strip()] == []


class TestPatternsPageBindings:
    @pytest.mark.parametrize("name", BOUND_NAMES)
    def test_binding_is_present(self, all_tabs_html, name):
        assert name in all_tabs_html


class TestPatternsPageTabs:
    @pytest.mark.parametrize("tab", TABS)
    def test_every_tab_renders(self, logged_in_admin, tab):
        """Each tab includes a different partial, so each is a separate chance to break."""
        response = logged_in_admin.get(f"{PATTERNS_URL}?tab={tab}")
        assert response.status_code == 200
        assert "backoffice/js/patterns.js" in response.get_data(as_text=True)
