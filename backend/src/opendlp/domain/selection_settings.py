"""ABOUTME: Selection settings domain model for sortition algorithm configuration
ABOUTME: Contains SelectionSettings shared by both CSV and GSheet assembly data sources"""

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, get_args

from sortition_algorithms import settings

from opendlp import config

Teams = Literal["aus", "eu", "uk", "other"]
VALID_TEAMS = get_args(Teams)
OTHER_TEAM = VALID_TEAMS[-1]
assert OTHER_TEAM == "other"

DEFAULT_ID_COLUMN: dict[str, str] = {
    "uk": "nationbuilder_id",
    "eu": "unique_id",
    "aus": "nationbuilder_id",
}
DEFAULT_ADDRESS_COLS: dict[str, list[str]] = {
    "uk": ["primary_address1", "zip_royal_mail"],
    "eu": ["address_line1", "postcode"],
    "aus": ["primary_address1", "primary_zip"],
}
DEFAULT_COLS_TO_KEEP: dict[str, list[str]] = {
    "uk": [
        "first_name",
        "last_name",
        "mobile_number",
        "email",
        "primary_address1",
        "primary_address2",
        "primary_city",
        "zip_royal_mail",
        "tag_list",
        "age",
        "gender",
    ],
    "eu": [
        "first_name",
        "last_name",
        "email",
        "phone_country",
        "phone_number",
        "address_line1",
        "address_line2",
        "city",
        "postcode",
        "country",
        "LocationNearest",
        "gender",
        "age",
        "nationality",
        "keep_informed",
    ],
    "aus": [
        "first_name",
        "last_name",
        "mobile_number",
        "email",
        "primary_address1",
        "primary_address2",
        "primary_city",
        "primary_zip",
        "tag_list",
        "age",
        "gender",
    ],
}


@dataclass
class SelectionSettings:
    """Selection algorithm settings shared across CSV and GSheet data sources."""

    assembly_id: uuid.UUID
    selection_settings_id: uuid.UUID | None = None
    id_column: str = "external_id"
    check_same_address: bool = True
    check_same_address_cols: list[str] = field(default_factory=list)
    columns_to_keep: list[str] = field(default_factory=list)
    selection_algorithm: str = "maximin"

    def to_settings(self) -> settings.Settings:
        return settings.Settings(
            id_column=self.id_column,
            columns_to_keep=self.columns_to_keep,
            check_same_address=self.check_same_address,
            check_same_address_columns=self.check_same_address_cols,
            selection_algorithm=self.selection_algorithm,
            solver_backend=config.get_solver_backend(),
        )

    def create_detached_copy(self) -> "SelectionSettings":
        return SelectionSettings(**asdict(self))

    @property
    def check_same_address_cols_string(self) -> str:
        return ", ".join(self.check_same_address_cols)

    @property
    def columns_to_keep_string(self) -> str:
        return ", ".join(self.columns_to_keep)

    @staticmethod
    def _str_to_list_str(string_with_commas: Any) -> list[str]:
        if string_with_commas is None:
            return []
        assert isinstance(string_with_commas, str)
        return [col.strip() for col in string_with_commas.split(",") if col.strip()]

    @classmethod
    def convert_str_kwargs(cls, **kwargs: Any) -> dict[str, Any]:
        """Auto convert string with commas into list of strings for two particular fields"""
        new_kwargs: dict[str, Any] = {}
        for field_name, value in kwargs.items():
            if field_name == "check_same_address_cols_string":
                field_name = "check_same_address_cols"
                value = cls._str_to_list_str(value)
            if field_name == "columns_to_keep_string":
                field_name = "columns_to_keep"
                value = cls._str_to_list_str(value)
            new_kwargs[field_name] = value
        return new_kwargs

    def update_from_str_kwargs(self, **kwargs: Any) -> None:
        converted = SelectionSettings.convert_str_kwargs(**kwargs)
        for key, value in converted.items():
            if hasattr(self, key):
                setattr(self, key, value)
