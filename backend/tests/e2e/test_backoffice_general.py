"""ABOUTME: End-to-end PostgreSQL happy-path smokes for general backoffice routes
ABOUTME: Behavioural coverage (showcase, data-source locking, render branches) lives in tests/component/"""


def test_dashboard_loads_for_logged_in_user(logged_in_admin):
    """Dashboard page loads successfully."""
    response = logged_in_admin.get("/backoffice/dashboard")
    assert response.status_code == 200
    assert b"Dashboard" in response.data or b"Assembly" in response.data.lower()


def test_the_old_data_address_lands_on_the_data_source_card(logged_in_admin, existing_assembly):
    """The Data Source tab is a card on the details page; its address redirects there."""
    response = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}/data", follow_redirects=True)
    assert response.status_code == 200
    assert b'id="data-source"' in response.data
