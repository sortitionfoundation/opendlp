"""ABOUTME: Unit tests for the one ordered list of registration questions and content blocks.
ABOUTME: Covers where new items go, adding/editing/removing blocks, moving and reordering, and the change timestamp."""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_content_block import (
    FormItemKind,
    FormItemRef,
    RegistrationContentBlock,
    form_item_ref,
)
from opendlp.domain.respondent_field_schema import (
    DerivationType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.exceptions import (
    ContentBlockInvalidError,
    ContentBlockNotFoundError,
    FieldDefinitionConflictError,
    InsufficientPermissions,
)
from opendlp.service_layer.respondent_field_schema_service import (
    add_content_block,
    add_field,
    delete_content_block,
    delete_field,
    get_form_items,
    initialise_empty_schema,
    move_form_item,
    reorder_form_items,
    update_content_block,
    update_field,
    update_schema_from_headers,
)
from tests.fakes import FakeUnitOfWork


@pytest.fixture
def uow():
    with FakeUnitOfWork() as entered:
        yield entered


@pytest.fixture
def admin(uow) -> User:
    user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    uow.users.add(user)
    return user


@pytest.fixture
def assembly(uow) -> Assembly:
    assembly = Assembly(title="Test Assembly", number_to_select=40)
    uow.assemblies.add(assembly)
    return assembly


def _keys(uow, user: User, assembly: Assembly) -> list[str]:
    """The list as the questions step shows it: field keys, and '# heading' for a block."""
    return [
        f"# {item.heading}" if isinstance(item, RegistrationContentBlock) else item.field_key
        for item in get_form_items(uow, user.id, assembly.id)
    ]


def _block(uow, assembly: Assembly, heading: str, sort_order: int) -> RegistrationContentBlock:
    block = RegistrationContentBlock(assembly_id=assembly.id, sort_order=sort_order, heading=heading)
    uow.registration_content_blocks.add(block)
    return block


def _field(uow, assembly: Assembly, key: str, sort_order: int, **kwargs) -> RespondentFieldDefinition:
    field = RespondentFieldDefinition(
        assembly_id=assembly.id,
        field_key=key,
        label=key,
        group=kwargs.pop("group", RespondentFieldGroup.OTHER),
        sort_order=sort_order,
        **kwargs,
    )
    uow.respondent_field_definitions.add(field)
    return field


def _derived(uow, assembly: Assembly, key: str, sort_order: int) -> RespondentFieldDefinition:
    return _field(
        uow,
        assembly,
        key,
        sort_order,
        group=RespondentFieldGroup.DERIVED,
        is_derived=True,
        derived_from=["source"],
        derivation_type=DerivationType.SMALL_MAPPING,
        derivation_config={"mapping": {}},
    )


class TestSeedingOrder:
    def test_an_empty_schema_starts_with_eligibility_and_ends_with_consent(self, uow, admin, assembly):
        initialise_empty_schema(uow, admin.id, assembly.id)

        assert _keys(uow, admin, assembly) == ["eligible", "can_attend", "email", "consent", "stay_on_db"]

    def test_a_csv_seed_keeps_the_csv_order_and_adds_no_headings(self, uow, admin, assembly):
        update_schema_from_headers(uow, assembly.id, ["id", "postcode", "first_name", "gender"], "id")

        assert _keys(uow, admin, assembly) == [
            "eligible",
            "can_attend",
            "email",
            "postcode",
            "first_name",
            "gender",
            "consent",
            "stay_on_db",
        ]

    def test_a_built_in_column_in_the_csv_stays_where_the_csv_puts_it(self, uow, admin, assembly):
        update_schema_from_headers(uow, assembly.id, ["id", "first_name", "email", "consent", "gender"], "id")

        assert _keys(uow, admin, assembly) == [
            "eligible",
            "can_attend",
            "first_name",
            "email",
            "consent",
            "gender",
            "stay_on_db",
        ]

    def test_a_later_upload_appends_new_columns_in_csv_order(self, uow, admin, assembly):
        update_schema_from_headers(uow, assembly.id, ["id", "first_name"], "id")
        add_content_block(uow, admin.id, assembly.id, heading="The end")

        update_schema_from_headers(uow, assembly.id, ["id", "zebra", "first_name", "apple"], "id")

        keys = _keys(uow, admin, assembly)
        assert keys[-3:] == ["# The end", "zebra", "apple"]


class TestAddingItems:
    def test_a_new_question_goes_at_the_end(self, uow, admin, assembly):
        _field(uow, assembly, "first", 10)
        _block(uow, assembly, "Heading", 20)

        add_field(uow, admin.id, assembly.id, "second")

        assert _keys(uow, admin, assembly) == ["first", "# Heading", "second"]

    def test_a_new_question_can_go_below_a_chosen_item(self, uow, admin, assembly):
        first = _field(uow, assembly, "first", 10)
        _field(uow, assembly, "last", 20)

        add_field(uow, admin.id, assembly.id, "middle", after=form_item_ref(first))

        assert _keys(uow, admin, assembly) == ["first", "middle", "last"]

    def test_an_unknown_item_to_go_below_puts_it_at_the_end(self, uow, admin, assembly):
        """The list changed since the page was drawn; the end is the safe place."""
        _field(uow, assembly, "first", 10)

        add_field(uow, admin.id, assembly.id, "second", after=FormItemRef(FormItemKind.BLOCK, uuid.uuid4()))

        assert _keys(uow, admin, assembly) == ["first", "second"]

    def test_a_new_question_goes_before_derived_fields_sorted_later(self, uow, admin, assembly):
        """Derived fields are not on the list, so their sort order must not push questions around."""
        _field(uow, assembly, "first", 10)
        _derived(uow, assembly, "region", 500)

        field = add_field(uow, admin.id, assembly.id, "second")

        assert field.sort_order == 20

    def test_a_block_goes_at_the_end(self, uow, admin, assembly):
        _field(uow, assembly, "first", 10)

        block = add_content_block(uow, admin.id, assembly.id, heading="About you", body_html="<p>Tell us</p>")

        assert _keys(uow, admin, assembly) == ["first", "# About you"]
        assert block.body_html == "<p>Tell us</p>"

    def test_a_block_can_go_below_a_chosen_item(self, uow, admin, assembly):
        first = _field(uow, assembly, "first", 10)
        _field(uow, assembly, "last", 20)

        add_content_block(uow, admin.id, assembly.id, heading="Between", after=form_item_ref(first))

        assert _keys(uow, admin, assembly) == ["first", "# Between", "last"]

    def test_an_empty_block_is_refused(self, uow, admin, assembly):
        with pytest.raises(ContentBlockInvalidError):
            add_content_block(uow, admin.id, assembly.id, heading="", body_html="<p></p>")

    def test_only_a_manager_can_add_a_block(self, uow, assembly):
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(user)

        with pytest.raises(InsufficientPermissions):
            add_content_block(uow, user.id, assembly.id, heading="Nope")


class TestEditingBlocks:
    def test_update_changes_heading_and_body(self, uow, admin, assembly):
        block = _block(uow, assembly, "Old", 10)

        updated = update_content_block(uow, admin.id, assembly.id, block.id, heading="New", body_html="<p>x</p>")

        assert updated.heading == "New"
        assert updated.body_html == "<p>x</p>"

    def test_update_refuses_an_empty_block(self, uow, admin, assembly):
        block = _block(uow, assembly, "Old", 10)

        with pytest.raises(ContentBlockInvalidError):
            update_content_block(uow, admin.id, assembly.id, block.id, heading=" ", body_html="")

    def test_update_of_a_block_in_another_assembly_is_not_found(self, uow, admin, assembly):
        other = Assembly(title="Other", number_to_select=1)
        uow.assemblies.add(other)
        block = _block(uow, other, "Theirs", 10)

        with pytest.raises(ContentBlockNotFoundError):
            update_content_block(uow, admin.id, assembly.id, block.id, heading="Mine")

    def test_delete_removes_the_block(self, uow, admin, assembly):
        block = _block(uow, assembly, "Gone", 10)
        _field(uow, assembly, "kept", 20)

        delete_content_block(uow, admin.id, assembly.id, block.id)

        assert _keys(uow, admin, assembly) == ["kept"]

    def test_delete_of_a_missing_block_is_not_found(self, uow, admin, assembly):
        with pytest.raises(ContentBlockNotFoundError):
            delete_content_block(uow, admin.id, assembly.id, uuid.uuid4())


class TestReorder:
    def test_reorder_sets_the_whole_list(self, uow, admin, assembly):
        a = _field(uow, assembly, "a", 10)
        heading = _block(uow, assembly, "H", 20)
        b = _field(uow, assembly, "b", 30)

        reorder_form_items(uow, admin.id, assembly.id, [form_item_ref(b), form_item_ref(a), form_item_ref(heading)])

        assert _keys(uow, admin, assembly) == ["b", "a", "# H"]
        assert [i.sort_order for i in get_form_items(uow, admin.id, assembly.id)] == [10, 20, 30]

    def test_reorder_refuses_an_incomplete_list(self, uow, admin, assembly):
        """A browser that missed someone else's change must not half-apply its order."""
        a = _field(uow, assembly, "a", 10)
        _field(uow, assembly, "b", 20)

        with pytest.raises(FieldDefinitionConflictError):
            reorder_form_items(uow, admin.id, assembly.id, [form_item_ref(a)])
        assert _keys(uow, admin, assembly) == ["a", "b"]

    def test_reorder_refuses_a_derived_field(self, uow, admin, assembly):
        a = _field(uow, assembly, "a", 10)
        region = _derived(uow, assembly, "region", 20)

        with pytest.raises(FieldDefinitionConflictError):
            reorder_form_items(uow, admin.id, assembly.id, [form_item_ref(a), form_item_ref(region)])


class TestMove:
    @pytest.fixture
    def items(self, uow, assembly) -> dict[str, FormItemRef]:
        made = [_field(uow, assembly, "a", 10), _block(uow, assembly, "H", 20), _field(uow, assembly, "b", 30)]
        return {"a": form_item_ref(made[0]), "H": form_item_ref(made[1]), "b": form_item_ref(made[2])}

    @pytest.mark.parametrize(
        ("name", "direction", "expected"),
        [
            ("H", "up", ["# H", "a", "b"]),
            ("H", "down", ["a", "b", "# H"]),
            ("b", "top", ["b", "a", "# H"]),
            ("a", "bottom", ["# H", "b", "a"]),
            ("a", "up", ["a", "# H", "b"]),
            ("b", "down", ["a", "# H", "b"]),
        ],
    )
    def test_moves(self, uow, admin, assembly, items, name, direction, expected):
        move_form_item(uow, admin.id, assembly.id, items[name], direction)

        assert _keys(uow, admin, assembly) == expected

    def test_a_question_moves_past_a_heading(self, uow, admin, assembly, items):
        """There are no sections to stay inside: a question crosses a heading like any other item."""
        move_form_item(uow, admin.id, assembly.id, items["b"], "up")

        assert _keys(uow, admin, assembly) == ["a", "b", "# H"]

    def test_an_unknown_direction_is_refused(self, uow, admin, assembly, items):
        with pytest.raises(ValueError):
            move_form_item(uow, admin.id, assembly.id, items["a"], "sideways")

    def test_moving_a_missing_item_is_not_found(self, uow, admin, assembly, items):
        with pytest.raises(ContentBlockNotFoundError):
            move_form_item(uow, admin.id, assembly.id, FormItemRef(FormItemKind.BLOCK, uuid.uuid4()), "up")


class TestQuestionsUpdatedAt:
    def _changed(self, uow, assembly: Assembly) -> bool:
        return uow.assemblies.get(assembly.id).questions_updated_at is not None

    def test_adding_a_block_records_a_change(self, uow, admin, assembly):
        add_content_block(uow, admin.id, assembly.id, heading="H")

        assert self._changed(uow, assembly)

    def test_deleting_a_block_records_a_change(self, uow, admin, assembly):
        block = _block(uow, assembly, "H", 10)

        delete_content_block(uow, admin.id, assembly.id, block.id)

        assert self._changed(uow, assembly)

    def test_deleting_a_question_records_a_change(self, uow, admin, assembly):
        """No row is left to carry an updated_at, which is why the timestamp lives on the assembly."""
        field = _field(uow, assembly, "a", 10)

        delete_field(uow, admin.id, assembly.id, field.id)

        assert self._changed(uow, assembly)

    def test_editing_a_question_records_a_change(self, uow, admin, assembly):
        field = _field(uow, assembly, "a", 10)

        update_field(uow, admin.id, assembly.id, field.id, label="A question")

        assert self._changed(uow, assembly)

    def test_moving_records_a_change(self, uow, admin, assembly):
        _field(uow, assembly, "a", 10)
        b = _field(uow, assembly, "b", 20)

        move_form_item(uow, admin.id, assembly.id, form_item_ref(b), "up")

        assert self._changed(uow, assembly)

    def test_seeding_records_a_change(self, uow, admin, assembly):
        initialise_empty_schema(uow, admin.id, assembly.id)

        assert self._changed(uow, assembly)

    def test_moving_past_the_end_records_no_change(self, uow, admin, assembly):
        _field(uow, assembly, "a", 10)
        last = _field(uow, assembly, "b", 20)

        move_form_item(uow, admin.id, assembly.id, form_item_ref(last), "down")

        assert uow.assemblies.get(assembly.id).questions_updated_at is None
