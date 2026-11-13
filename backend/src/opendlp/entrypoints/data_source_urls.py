"""ABOUTME: Where a request that changed a project's data goes back to
ABOUTME: The data source settings dialog on the project details page when the dialog sent it, else the Data Source tab"""

import uuid

from flask import request, url_for


def data_source_return_url(assembly_id: uuid.UUID, source: str = "") -> str:
    """The page to show after deleting data or removing a Google Sheet's settings."""
    if request.form.get("return_to") == "dialog":
        return url_for("backoffice.view_assembly", assembly_id=assembly_id, data_source=1)
    if source:
        return url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source=source)
    return url_for("backoffice.view_assembly_data", assembly_id=assembly_id)
