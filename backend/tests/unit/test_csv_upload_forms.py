"""ABOUTME: Unit tests for CSV upload form validation
ABOUTME: Tests UploadTargetsCsvForm field validation"""

import io

import pytest
from flask import Flask
from werkzeug.datastructures import FileStorage

from opendlp.entrypoints.flask_app import create_app
from opendlp.entrypoints.forms import UploadTargetsCsvForm


@pytest.fixture
def app() -> Flask:
    return create_app("testing")


def _make_file_storage(filename: str, content: bytes = b"data") -> FileStorage:
    """Create a FileStorage object for testing."""
    return FileStorage(
        stream=io.BytesIO(content),
        filename=filename,
        content_type="text/csv" if filename.endswith(".csv") else "application/octet-stream",
    )


class TestUploadTargetsCsvForm:
    def test_requires_csv_file(self, app):
        with app.test_request_context():
            form = UploadTargetsCsvForm(data={})
            assert not form.validate()
            assert "csv_file" in form.errors

    def test_rejects_non_csv_file(self, app):
        with app.test_request_context(
            method="POST",
            content_type="multipart/form-data",
            data={"csv_file": _make_file_storage("targets.txt")},
        ):
            form = UploadTargetsCsvForm()
            assert not form.validate()
            assert "csv_file" in form.errors

    def test_accepts_valid_csv_file(self, app):
        with app.test_request_context(
            method="POST",
            content_type="multipart/form-data",
            data={"csv_file": _make_file_storage("targets.csv", b"feature,value,min,max\n")},
        ):
            form = UploadTargetsCsvForm()
            assert form.validate()

    def test_has_no_replace_existing_field(self, app):
        with app.test_request_context():
            form = UploadTargetsCsvForm()
            assert not hasattr(form, "replace_existing")
