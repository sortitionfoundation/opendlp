"""ABOUTME: Unit tests for targets blueprint routes
ABOUTME: Tests route registration, authentication requirements, and basic request handling"""

import uuid

import pytest
from flask.testing import FlaskClient

from opendlp.entrypoints.flask_app import create_app


class TestTargetsRoutes:
    @pytest.fixture
    def client(self) -> FlaskClient:
        app = create_app("testing")
        return app.test_client()

    def test_targets_blueprint_registered(self) -> None:
        app = create_app("testing")
        blueprint_names = [bp.name for bp in app.blueprints.values()]
        assert "targets_legacy" in blueprint_names

    def test_targets_route_requires_login(self, client: FlaskClient) -> None:
        assembly_id = uuid.uuid4()
        response = client.get(f"/assemblies/{assembly_id}/targets")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_targets_upload_route_requires_login(self, client: FlaskClient) -> None:
        assembly_id = uuid.uuid4()
        response = client.post(f"/assemblies/{assembly_id}/targets/upload")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_targets_route_invalid_assembly_id(self, client: FlaskClient) -> None:
        response = client.get("/assemblies/not-a-uuid/targets")
        assert response.status_code == 404

    def test_add_category_requires_login(self, client: FlaskClient) -> None:
        assembly_id = uuid.uuid4()
        response = client.post(f"/assemblies/{assembly_id}/targets/categories")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_edit_category_requires_login(self, client: FlaskClient) -> None:
        assembly_id = uuid.uuid4()
        category_id = uuid.uuid4()
        response = client.post(f"/assemblies/{assembly_id}/targets/categories/{category_id}")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_delete_category_requires_login(self, client: FlaskClient) -> None:
        assembly_id = uuid.uuid4()
        category_id = uuid.uuid4()
        response = client.post(f"/assemblies/{assembly_id}/targets/categories/{category_id}/delete")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_add_value_requires_login(self, client: FlaskClient) -> None:
        assembly_id = uuid.uuid4()
        category_id = uuid.uuid4()
        response = client.post(f"/assemblies/{assembly_id}/targets/categories/{category_id}/values")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_edit_value_requires_login(self, client: FlaskClient) -> None:
        assembly_id = uuid.uuid4()
        category_id = uuid.uuid4()
        value_id = uuid.uuid4()
        response = client.post(f"/assemblies/{assembly_id}/targets/categories/{category_id}/values/{value_id}")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_delete_value_requires_login(self, client: FlaskClient) -> None:
        assembly_id = uuid.uuid4()
        category_id = uuid.uuid4()
        value_id = uuid.uuid4()
        response = client.post(f"/assemblies/{assembly_id}/targets/categories/{category_id}/values/{value_id}/delete")
        assert response.status_code == 302
        assert "/auth/login" in response.location
