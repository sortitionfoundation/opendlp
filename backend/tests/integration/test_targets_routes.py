"""ABOUTME: Integration tests for targets blueprint routes
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
        assert "targets" in blueprint_names

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
