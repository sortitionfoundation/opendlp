"""ABOUTME: Unit tests for respondents blueprint routes
ABOUTME: Tests route registration, authentication requirements, and basic request handling"""

import uuid

import pytest
from flask.testing import FlaskClient

from opendlp.entrypoints.flask_app import create_app


class TestRespondentsRoutes:
    @pytest.fixture
    def client(self) -> FlaskClient:
        app = create_app("testing")
        return app.test_client()

    def test_respondents_blueprint_registered(self) -> None:
        app = create_app("testing")
        blueprint_names = [bp.name for bp in app.blueprints.values()]
        assert "respondents" in blueprint_names

    def test_respondents_route_requires_login(self, client: FlaskClient) -> None:
        assembly_id = uuid.uuid4()
        response = client.get(f"/assemblies/{assembly_id}/respondents")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_respondents_upload_route_requires_login(self, client: FlaskClient) -> None:
        assembly_id = uuid.uuid4()
        response = client.post(f"/assemblies/{assembly_id}/respondents/upload")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_respondents_route_invalid_assembly_id(self, client: FlaskClient) -> None:
        response = client.get("/assemblies/not-a-uuid/respondents")
        assert response.status_code == 404
