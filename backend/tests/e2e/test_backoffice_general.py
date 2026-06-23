"""ABOUTME: End-to-end PostgreSQL happy-path smokes for general backoffice routes
ABOUTME: Behavioural coverage (showcase, data-source locking, render branches) lives in tests/component/"""


def test_dashboard_loads_for_logged_in_user(logged_in_admin):
    """Dashboard page loads successfully."""
    response = logged_in_admin.get("/backoffice/dashboard")
    assert response.status_code == 200
    assert b"Dashboard" in response.data or b"Assembly" in response.data.lower()


def test_view_assembly_data_page_loads(logged_in_admin, existing_assembly):
    """The assembly data page loads successfully."""
    response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data")
    assert response.status_code == 200
    assert b"Data Source" in response.data or b"data" in response.data.lower()
