"""ABOUTME: Unit tests for create_app wiring the UnitOfWork factory onto the app
ABOUTME: Verifies the default is registered and a custom factory can be injected"""

from opendlp import bootstrap
from opendlp.entrypoints.flask_app import create_app


class TestCreateAppUowFactory:
    def test_registers_default_factory(self) -> None:
        """With no override, create_app registers the production default factory."""
        app = create_app("testing")
        assert app.extensions["uow_factory"] is bootstrap.default_uow_factory

    def test_accepts_custom_factory(self) -> None:
        """An injected factory is stored on the app for get_flask_uow to resolve."""

        def fake_factory() -> object:
            return object()

        app = create_app("testing", uow_factory=fake_factory)
        assert app.extensions["uow_factory"] is fake_factory

    def test_get_flask_uow_resolves_injected_factory(self) -> None:
        """End to end: get_flask_uow inside the app returns the injected product."""
        sentinel_uow = object()
        app = create_app("testing", uow_factory=lambda: sentinel_uow)

        with app.app_context():
            assert bootstrap.get_flask_uow() is sentinel_uow
