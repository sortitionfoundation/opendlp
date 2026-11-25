"""ABOUTME: End-to-end PostgreSQL happy-path smokes for general backoffice routes
ABOUTME: Behavioural coverage (showcase, data-source locking, render branches) lives in tests/component/"""


def test_dashboard_loads_for_logged_in_user(logged_in_admin):
    """Dashboard page loads successfully."""
    response = logged_in_admin.get("/backoffice/dashboard")
    assert response.status_code == 200
    assert b"Your projects" in response.data


def test_the_old_data_address_lands_on_the_data_source_card(logged_in_admin, existing_assembly):
    """The Data Source tab is a card on the details page; its address redirects there."""
    response = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}/data", follow_redirects=True)
    assert response.status_code == 200
    assert b'id="data-source"' in response.data


def test_the_address_of_a_retired_project_page_lands_on_the_project(logged_in_admin, existing_assembly):
    """An old /assemblies/<id> bookmark redirects to the backoffice project page."""
    response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}", follow_redirects=True)
    assert response.status_code == 200
    assert response.request.path == f"/backoffice/project/{existing_assembly.id}"
    assert existing_assembly.title.encode() in response.data


def test_the_address_of_the_retired_dashboard_lands_on_the_list_of_projects(logged_in_admin):
    response = logged_in_admin.get("/dashboard", follow_redirects=True)
    assert response.status_code == 200
    assert response.request.path == "/backoffice/dashboard"
