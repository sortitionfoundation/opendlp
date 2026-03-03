"""ABOUTME: Unit tests for CSV upload form validation
ABOUTME: Tests UploadTargetsCsvForm and UploadRespondentsCsvForm field validation"""

import io

import pytest
from flask import Flask
from werkzeug.datastructures import FileStorage

from opendlp.entrypoints.flask_app import create_app
from opendlp.entrypoints.forms import UploadRespondentsCsvForm, UploadTargetsCsvForm


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


class TestUploadRespondentsCsvForm:
    def test_requires_csv_file(self, app):
        with app.test_request_context():
            form = UploadRespondentsCsvForm(data={})
            assert not form.validate()
            assert "csv_file" in form.errors

    def test_rejects_non_csv_file(self, app):
        with app.test_request_context(
            method="POST",
            content_type="multipart/form-data",
            data={"csv_file": _make_file_storage("respondents.xlsx")},
        ):
            form = UploadRespondentsCsvForm()
            assert not form.validate()
            assert "csv_file" in form.errors

    def test_accepts_valid_csv_file(self, app):
        with app.test_request_context(
            method="POST",
            content_type="multipart/form-data",
            data={"csv_file": _make_file_storage("respondents.csv", b"external_id,email\n")},
        ):
            form = UploadRespondentsCsvForm()
            assert form.validate()

    def test_id_column_is_optional(self, app):
        with app.test_request_context(
            method="POST",
            content_type="multipart/form-data",
            data={"csv_file": _make_file_storage("respondents.csv", b"data")},
        ):
            form = UploadRespondentsCsvForm()
            assert form.validate()
            assert form.id_column.data is None or form.id_column.data == ""

    def test_id_column_respects_max_length(self, app):
        with app.test_request_context(
            method="POST",
            content_type="multipart/form-data",
            data={
                "csv_file": _make_file_storage("respondents.csv", b"data"),
                "id_column": "x" * 101,
            },
        ):
            form = UploadRespondentsCsvForm()
            assert not form.validate()
            assert "id_column" in form.errors

    def test_replace_existing_defaults_to_true(self, app):
        with app.test_request_context():
            form = UploadRespondentsCsvForm()
            assert form.replace_existing.data is True
