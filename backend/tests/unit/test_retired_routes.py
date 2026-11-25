"""ABOUTME: Unit tests for which routes the app registers under the addresses of the retired pages
ABOUTME: Only the home page and two redirects are left outside /backoffice, /admin, /auth and /profile"""

from opendlp.entrypoints.flask_app import create_app


def _rules_starting(prefix: str) -> dict[str, str]:
    app = create_app("testing")
    return {rule.rule: rule.endpoint for rule in app.url_map.iter_rules() if rule.rule.startswith(prefix)}


def test_no_retired_blueprint_is_registered() -> None:
    app = create_app("testing")
    assert [name for name in app.blueprints if name.endswith("_legacy")] == []


def test_the_only_route_under_assemblies_is_the_redirect() -> None:
    assert _rules_starting("/assemblies") == {"/assemblies/<uuid:assembly_id>": "main.assembly_redirect"}


def test_the_old_dashboard_is_a_redirect() -> None:
    assert _rules_starting("/dashboard") == {"/dashboard": "main.dashboard_redirect"}


def test_main_holds_the_home_page_and_the_two_redirects() -> None:
    app = create_app("testing")
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules() if rule.endpoint.startswith("main.")}
    assert endpoints == {"main.index", "main.dashboard_redirect", "main.assembly_redirect"}
