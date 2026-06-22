"""ABOUTME: Unit tests for the Flask UnitOfWork seam (get_flask_uow / factory)
ABOUTME: Verifies get_flask_uow resolves the app-registered factory or the default"""

from flask import Flask

from opendlp import bootstrap


def _app_with_factory(factory: bootstrap.UowFactory) -> Flask:
    """A minimal Flask app with a UoW factory registered the way create_app does."""
    app = Flask(__name__)
    app.extensions["uow_factory"] = factory
    return app


class TestFlaskUowSeam:
    def test_get_flask_uow_uses_configured_factory(self) -> None:
        """get_flask_uow returns whatever the app-configured factory produces."""
        sentinel_uow = object()
        app = _app_with_factory(lambda: sentinel_uow)

        with app.app_context():
            assert bootstrap.get_flask_uow() is sentinel_uow

    def test_get_flask_uow_factory_returns_configured_factory(self) -> None:
        """get_flask_uow_factory returns the factory itself, for multi-use callers."""

        def fake_factory() -> object:
            return object()

        app = _app_with_factory(fake_factory)
        with app.app_context():
            assert bootstrap.get_flask_uow_factory() is fake_factory

    def test_falls_back_to_default_when_not_registered(self) -> None:
        """If no factory is registered on the app, the default is used."""
        bare_app = Flask(__name__)  # nothing registered, so extensions is empty

        with bare_app.app_context():
            assert bootstrap.get_flask_uow_factory() is bootstrap.default_uow_factory
