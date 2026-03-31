"""ABOUTME: Unit tests for SelectionSettings domain model
ABOUTME: Tests creation, validation, to_settings conversion, detached copy, and string conversion"""

import uuid

from sortition_algorithms.settings import Settings

from opendlp.domain.selection_settings import SelectionSettings


class TestSelectionSettings:
    """Test SelectionSettings domain model"""

    def test_create_with_defaults(self):
        """Test creating SelectionSettings with default values"""
        assembly_id = uuid.uuid4()
        sel_settings = SelectionSettings(assembly_id=assembly_id)

        assert sel_settings.assembly_id == assembly_id
        assert sel_settings.selection_settings_id is None
        assert sel_settings.id_column == "external_id"
        assert sel_settings.check_same_address is True
        assert sel_settings.check_same_address_cols == []
        assert sel_settings.columns_to_keep == []
        assert sel_settings.selection_algorithm == "maximin"

    def test_create_with_custom_values(self):
        """Test creating SelectionSettings with custom values"""
        assembly_id = uuid.uuid4()
        settings_id = uuid.uuid4()

        sel_settings = SelectionSettings(
            assembly_id=assembly_id,
            selection_settings_id=settings_id,
            id_column="custom_id",
            check_same_address=False,
            check_same_address_cols=["address", "postcode"],
            columns_to_keep=["name", "email", "age"],
            selection_algorithm="random",
        )

        assert sel_settings.assembly_id == assembly_id
        assert sel_settings.selection_settings_id == settings_id
        assert sel_settings.id_column == "custom_id"
        assert sel_settings.check_same_address is False
        assert sel_settings.check_same_address_cols == ["address", "postcode"]
        assert sel_settings.columns_to_keep == ["name", "email", "age"]
        assert sel_settings.selection_algorithm == "random"

    def test_to_settings_conversion(self):
        """Test converting SelectionSettings to sortition-algorithms Settings"""
        assembly_id = uuid.uuid4()
        sel_settings = SelectionSettings(
            assembly_id=assembly_id,
            id_column="participant_id",
            check_same_address=True,
            check_same_address_cols=["street", "zip"],
            columns_to_keep=["first_name", "last_name", "email"],
            selection_algorithm="nash",
        )

        settings = sel_settings.to_settings()

        assert isinstance(settings, Settings)
        assert settings.id_column == "participant_id"
        assert settings.check_same_address is True
        assert settings.check_same_address_columns == ["street", "zip"]
        assert settings.columns_to_keep == ["first_name", "last_name", "email"]
        assert settings.selection_algorithm == "nash"

    def test_to_settings_with_defaults(self):
        """Test to_settings with default values"""
        assembly_id = uuid.uuid4()
        sel_settings = SelectionSettings(assembly_id=assembly_id, check_same_address=False)

        settings = sel_settings.to_settings()

        assert isinstance(settings, Settings)
        assert settings.id_column == "external_id"
        assert settings.check_same_address is False
        assert settings.check_same_address_columns == []
        assert settings.columns_to_keep == []
        assert settings.selection_algorithm == "maximin"

    def test_create_detached_copy(self):
        """Test creating a detached copy of SelectionSettings"""
        assembly_id = uuid.uuid4()
        settings_id = uuid.uuid4()

        original = SelectionSettings(
            assembly_id=assembly_id,
            selection_settings_id=settings_id,
            id_column="test_id",
            check_same_address=False,
            check_same_address_cols=["col1", "col2"],
            columns_to_keep=["col3", "col4"],
            selection_algorithm="stratified",
        )

        copy = original.create_detached_copy()

        # Verify all fields are copied
        assert copy.assembly_id == original.assembly_id
        assert copy.selection_settings_id == original.selection_settings_id
        assert copy.id_column == original.id_column
        assert copy.check_same_address == original.check_same_address
        assert copy.check_same_address_cols == original.check_same_address_cols
        assert copy.columns_to_keep == original.columns_to_keep
        assert copy.selection_algorithm == original.selection_algorithm

        # Verify it's a different object
        assert copy is not original

        # Verify lists are copies, not references
        assert copy.check_same_address_cols is not original.check_same_address_cols
        assert copy.columns_to_keep is not original.columns_to_keep

    def test_check_same_address_cols_string_property(self):
        """Test check_same_address_cols_string property converts list to comma-separated string."""
        sel_settings = SelectionSettings(
            assembly_id=uuid.uuid4(),
            check_same_address_cols=["primary_address1", "zip_royal_mail", "city"],
        )

        assert sel_settings.check_same_address_cols_string == "primary_address1, zip_royal_mail, city"

    def test_check_same_address_cols_string_property_empty_list(self):
        """Test check_same_address_cols_string property with empty list."""
        sel_settings = SelectionSettings(assembly_id=uuid.uuid4(), check_same_address_cols=[])

        assert sel_settings.check_same_address_cols_string == ""

    def test_columns_to_keep_string_property(self):
        """Test columns_to_keep_string property converts list to comma-separated string."""
        sel_settings = SelectionSettings(
            assembly_id=uuid.uuid4(),
            columns_to_keep=["first_name", "last_name", "email", "mobile_number"],
        )

        assert sel_settings.columns_to_keep_string == "first_name, last_name, email, mobile_number"

    def test_columns_to_keep_string_property_empty_list(self):
        """Test columns_to_keep_string property with empty list."""
        sel_settings = SelectionSettings(assembly_id=uuid.uuid4(), columns_to_keep=[])

        assert sel_settings.columns_to_keep_string == ""

    def test_convert_str_kwargs_address_cols(self):
        """Test convert_str_kwargs method updates check_same_address_cols from string."""
        kwargs = dict(
            assembly_id=uuid.uuid4(),
            check_same_address_cols_string="address1, postal_code, city",
        )
        sel_settings = SelectionSettings(**SelectionSettings.convert_str_kwargs(**kwargs))

        assert sel_settings.check_same_address_cols == ["address1", "postal_code", "city"]

    def test_convert_str_kwargs_columns_to_keep(self):
        """Test convert_str_kwargs method updates columns_to_keep from string."""
        kwargs = dict(
            assembly_id=uuid.uuid4(),
            columns_to_keep_string="first_name, last_name, email",
        )
        sel_settings = SelectionSettings(**SelectionSettings.convert_str_kwargs(**kwargs))

        assert sel_settings.columns_to_keep == ["first_name", "last_name", "email"]

    def test_convert_str_kwargs_both_fields(self):
        """Test convert_str_kwargs method updates both fields simultaneously."""
        kwargs = dict(
            assembly_id=uuid.uuid4(),
            check_same_address_cols_string="street, postcode",
            columns_to_keep_string="name, email, phone",
        )
        sel_settings = SelectionSettings(**SelectionSettings.convert_str_kwargs(**kwargs))

        assert sel_settings.check_same_address_cols == ["street", "postcode"]
        assert sel_settings.columns_to_keep == ["name", "email", "phone"]

    def test_convert_str_kwargs_with_spaces_and_empty_values(self):
        """Test convert_str_kwargs handles extra spaces and empty values."""
        kwargs = dict(
            assembly_id=uuid.uuid4(),
            check_same_address_cols_string="  address1 ,  , postal_code ,  city  ",
            columns_to_keep_string="first_name, , last_name,  email , ",
        )
        sel_settings = SelectionSettings(**SelectionSettings.convert_str_kwargs(**kwargs))

        assert sel_settings.check_same_address_cols == ["address1", "postal_code", "city"]
        assert sel_settings.columns_to_keep == ["first_name", "last_name", "email"]

    def test_convert_str_kwargs_empty_strings(self):
        """Test convert_str_kwargs with empty strings produces empty lists."""
        kwargs = dict(
            assembly_id=uuid.uuid4(),
            check_same_address_cols_string="",
            columns_to_keep_string="",
        )
        sel_settings = SelectionSettings(**SelectionSettings.convert_str_kwargs(**kwargs))

        assert sel_settings.check_same_address_cols == []
        assert sel_settings.columns_to_keep == []
