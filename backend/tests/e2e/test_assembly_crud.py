"""ABOUTME: End-to-end PostgreSQL happy-path smokes for Assembly CRUD
ABOUTME: Behavioural coverage (validation, permissions, render, not-found) lives in tests/component/"""

from datetime import UTC, datetime, timedelta

from tests.e2e.helpers import get_csrf_token


class TestAssemblyListView:
    """Test Assembly list view functionality - the dashboard for now."""

    def test_assemblies_list_empty_state(self, logged_in_admin):
        """Test assemblies list shows empty state when no assemblies exist."""
        response = logged_in_admin.get("/dashboard")
        assert response.status_code == 200
        assert b"Assemblies" in response.data
        assert b"You don" in response.data or b"no assemblies" in response.data


class TestAssemblyCreateView:
    """Test Assembly creation functionality."""

    def test_create_assembly_success(self, logged_in_admin):
        """Test successful assembly creation."""
        future_date = (datetime.now(UTC) + timedelta(days=30)).date()
        response = logged_in_admin.post(
            "/assemblies/new",
            data={
                "title": "New Test Assembly",
                "question": "What should we discuss in this assembly?",
                "first_assembly_date": future_date.strftime("%Y-%m-%d"),
                "number_to_select": "50",
                "csrf_token": get_csrf_token(logged_in_admin, "/assemblies/new"),
            },
            follow_redirects=False,
        )

        # Should redirect to view assembly page
        assert response.status_code == 302
        assert "/assemblies/" in response.location

        # Check flash message
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("created successfully" in msg for msg in flash_messages)


class TestAssemblyEditView:
    """Test Assembly editing functionality."""

    def test_edit_assembly_success(self, logged_in_admin, existing_assembly):
        """Test successful assembly editing."""
        updated_title = "Updated Assembly Title"
        updated_question = "What is the updated question?"
        future_date = (datetime.now(UTC) + timedelta(days=45)).date()

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/edit",
            data={
                "title": updated_title,
                "question": updated_question,
                "first_assembly_date": future_date.strftime("%Y-%m-%d"),
                "number_to_select": "100",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/edit"),
            },
            follow_redirects=False,
        )

        # Should redirect to view assembly page
        assert response.status_code == 302
        assert f"/assemblies/{existing_assembly.id}" in response.location

        # Check flash message
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("updated successfully" in msg for msg in flash_messages)


class TestAssemblyWorkflowIntegration:
    """Test complete assembly workflows end-to-end."""

    def test_complete_create_view_edit_workflow(self, logged_in_admin):
        """Test complete workflow: create -> view -> edit assembly."""
        # Step 1: Create assembly
        future_date = (datetime.now(UTC) + timedelta(days=60)).date()
        create_response = logged_in_admin.post(
            "/assemblies/new",
            data={
                "title": "Workflow Test Assembly",
                "question": "What should we test?",
                "first_assembly_date": future_date.strftime("%Y-%m-%d"),
                "number_to_select": "30",
                "csrf_token": get_csrf_token(logged_in_admin, "/assemblies/new"),
            },
            follow_redirects=False,
        )

        assert create_response.status_code == 302
        assembly_url = create_response.location

        # Step 2: View the created assembly
        view_response = logged_in_admin.get(assembly_url)
        assert view_response.status_code == 200
        assert b"Workflow Test Assembly" in view_response.data
        assert b"What should we test?" in view_response.data

        # Step 3: Edit the assembly
        assembly_id = assembly_url.split("/")[-1]
        updated_date = (datetime.now(UTC) + timedelta(days=90)).date()
        edit_response = logged_in_admin.post(
            f"/assemblies/{assembly_id}/edit",
            data={
                "title": "Updated Workflow Test Assembly",
                "question": "What should we test after update?",
                "first_assembly_date": updated_date.strftime("%Y-%m-%d"),
                "number_to_select": "40",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{assembly_id}/edit"),
            },
            follow_redirects=False,
        )

        assert edit_response.status_code == 302
        assert f"/assemblies/{assembly_id}" in edit_response.location

        # Step 4: Verify the update
        final_view_response = logged_in_admin.get(f"/assemblies/{assembly_id}")
        assert final_view_response.status_code == 200
        assert b"Updated Workflow Test Assembly" in final_view_response.data
        assert b"What should we test after update?" in final_view_response.data
