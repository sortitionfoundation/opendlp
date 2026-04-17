# Delete respondents — implementation plan

GDPR "right to be forgotten" support for respondents. A deleted respondent keeps its row (so historical selections still reference a valid ID) but all personal data is blanked and the status becomes `DELETED`. A comment trail is added to every respondent and is required when deleting.

## Design decisions (already agreed)

- **Enum change**: `RespondentStatus.EXCLUDED` (unused anywhere in live code) is replaced with `RespondentStatus.DELETED = "DELETED"`.
- **External ID**: `external_id` is a sequence number, not PII. It is **not** cleared on delete.
- **Fields scrubbed on delete**:
  - `email` → `""`
  - `attributes` → keys preserved, values blanked to `""` (keeps column-key stability for code that expects consistent keys across respondents)
  - `source_reference` → `""`
  - `consent`, `stay_on_db`, `eligible`, `can_attend` → `None` (all four are already typed `bool | None` on the domain; no type changes needed)
  - `selection_run_id` → `None`
  - `selection_status` → `RespondentStatus.DELETED`
  - `updated_at` → now (UTC)
  - `source_type` kept as-is
  - `created_at` kept as-is
  - `external_id` kept as-is
- **Comments storage**: JSON list on the `Respondent` row (not a separate table). Fits the existing "variable data as JSON" pattern.
- **Permissions**: gated on `can_manage_assembly` (i.e. admins, global organisers, and assembly managers — "users with assembly management rights").
- **Comment required on deletion**: the service function requires a non-empty comment, stored as a `RespondentComment` entry authored by the deleting user.
- **Default visibility of DELETED respondents**: excluded by default from `get_respondents_for_assembly` and repository queries; opt-in `include_deleted` flag for callers that need them.
- **Sortition data adapter**: **unchanged**. `eligible_only=True` already filters by `POOL` so DELETED is naturally excluded from live selection runs. `eligible_only=False` is used by `generate_selection_csvs` in `sortition.py`; that path must continue to return DELETED respondents so historical CSVs render with the right external_id and blank values. (The authoritative list for historical CSVs is `SelectionRunRecord.selected_ids` / `remaining_ids`; `selection_run_id` on the respondent row is not used by that flow.)

## 1 — Enum change

File: `src/opendlp/domain/value_objects.py`

Replace:

```python
class RespondentStatus(Enum):
    POOL = "POOL"
    SELECTED = "SELECTED"
    CONFIRMED = "CONFIRMED"
    WITHDRAWN = "WITHDRAWN"
    PARTICIPATED = "PARTICIPATED"
    EXCLUDED = "EXCLUDED"
```

with:

```python
class RespondentStatus(Enum):
    POOL = "POOL"
    SELECTED = "SELECTED"
    CONFIRMED = "CONFIRMED"
    WITHDRAWN = "WITHDRAWN"
    PARTICIPATED = "PARTICIPATED"
    DELETED = "DELETED"
```

## 2 — Domain model changes

File: `src/opendlp/domain/respondents.py`

### 2.1 New `RespondentAction` enum

In `src/opendlp/domain/value_objects.py` (next to `RespondentStatus`):

```python
class RespondentAction(Enum):
    """Type of action a RespondentComment records.

    NONE is a plain comment with no system action attached.
    EDIT records a change to the respondent's details.
    DELETE records a GDPR personal-data deletion.
    """

    NONE = "NONE"
    EDIT = "EDIT"
    DELETE = "DELETE"
```

### 2.2 New `RespondentComment` dataclass

```python
@dataclass(frozen=True)
class RespondentComment:
    text: str
    author_id: uuid.UUID
    created_at: datetime
    action: RespondentAction = RespondentAction.NONE

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "author_id": str(self.author_id),
            "created_at": self.created_at.isoformat(),
            "action": self.action.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RespondentComment":
        return cls(
            text=data["text"],
            author_id=uuid.UUID(data["author_id"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            # Default to NONE for rows written before the action field existed.
            action=RespondentAction(data.get("action", RespondentAction.NONE.value)),
        )
```

The action is stored alongside the comment so the UI can render a deletion banner (and, later, "edited by X at Y" entries) without inferring intent from free-text content. Old JSON rows without an `action` key decode as `NONE` — handled explicitly in `from_dict`.

### 2.3 Reserved field names

Add `"comments"` to `_RESERVED_FIELD_NAMES` so attribute keys can't shadow the new column.

### 2.4 Respondent constructor

Add `comments: list[RespondentComment] | None = None` parameter. Store as `self.comments = comments or []`.

Update `create_detached_copy` to include `comments=list(self.comments)`.

### 2.5 New methods

```python
def add_comment(
    self,
    text: str,
    author_id: uuid.UUID,
    action: RespondentAction = RespondentAction.NONE,
) -> None:
    """Append a comment authored by the given user."""
    text = text.strip()
    if not text:
        raise ValueError("Comment text is required")
    self.comments.append(
        RespondentComment(
            text=text,
            author_id=author_id,
            created_at=datetime.now(UTC),
            action=action,
        )
    )
    self.updated_at = datetime.now(UTC)

def delete_personal_data(self, author_id: uuid.UUID, comment: str) -> None:
    """Blank PII, flip status to DELETED, append the deletion comment.

    Keeps: id, external_id, assembly_id, source_type, created_at, comments.
    Blanks: email, attributes values, source_reference.
    Clears: consent, stay_on_db, eligible, can_attend, selection_run_id.
    The appended comment is tagged RespondentAction.DELETE.
    """
    comment = comment.strip()
    if not comment:
        raise ValueError("A comment is required when deleting personal data")
    self.selection_status = RespondentStatus.DELETED
    self.selection_run_id = None
    self.email = ""
    self.source_reference = ""
    self.consent = None
    self.stay_on_db = None
    self.eligible = None
    self.can_attend = None
    self.attributes = {key: "" for key in self.attributes}
    self.add_comment(comment, author_id, action=RespondentAction.DELETE)  # sets updated_at
```

### 2.6 Equality / hashing

No change — still based on `id`.

## 3 — ORM and migration

File: `src/opendlp/adapters/orm.py`

Add column to the `respondents` table:

```python
Column("comments", JSON, nullable=False, default=list),
```

Ensure the imperative mapper wires `comments` as a list of `RespondentComment` objects. The simplest path is a SQLAlchemy `TypeDecorator` similar to the existing JSON-backed columns that serialises/deserialises the list, or explicit conversion in the repository layer. Prefer a small `RespondentCommentListJSON` `TypeDecorator` in `orm.py` alongside the existing JSON-backed custom types, so the mapper handles conversion and we don't have to sprinkle it through the repo.

Migration:

```bash
uv run alembic revision --autogenerate -m "add comments and deleted status to respondents"
```

Verify the generated migration:

- Adds `comments` column with `server_default='[]'` (so existing rows get an empty list).
- No schema change for the enum (it is stored via `EnumAsString`).

## 4 — Repository interface

File: `src/opendlp/service_layer/repositories.py`

Update `RespondentRepository`:

- `get_by_assembly_id`: add `include_deleted: bool = False` parameter.
- `count_by_assembly_id`: add `include_deleted: bool = False` parameter.
- `count_non_pool`: change internal semantics to exclude DELETED (no signature change; document that DELETED is always excluded from this count).
- `reset_all_to_pool`: no signature change; document that DELETED respondents are skipped.
- `get_attribute_columns`, `get_attribute_value_counts`, `get_selected_attribute_value_counts`: no signature change; DELETED excluded internally.

Add a new abstract method:

```python
@abc.abstractmethod
def update(self, item: Respondent) -> None:
    """Persist changes to an existing respondent."""
    raise NotImplementedError
```

(Only needed if the current imperative mapping doesn't dirty-track automatically. Verify before adding — if the existing code mutates domain objects inside a `with uow:` block and commits successfully, we can skip this abstract method.)

## 5 — SQLAlchemy repository

File: `src/opendlp/adapters/sql_repository.py`

- `get_by_assembly_id(assembly_id, status=None, eligible_only=False, include_deleted=False)`:
  - When `include_deleted` is False **and** `status` is None, filter `selection_status != DELETED`.
  - When `status` is passed explicitly (even if `status == DELETED`), honour that filter and don't apply the exclude.
- `count_by_assembly_id(assembly_id, include_deleted=False)`: mirror the exclusion logic.
- `count_non_pool(assembly_id)`: filter `selection_status != POOL AND selection_status != DELETED`.
- `reset_all_to_pool(assembly_id)`:
  - Count: exclude DELETED from the count of affected rows.
  - Update: `WHERE assembly_id = :id AND selection_status != DELETED`.
- `get_attribute_columns(assembly_id)`: filter out DELETED when picking the sample row (prevents picking a respondent whose values are all blanked — the keys are still there, but better to pick a live row for consistency).
- `get_attribute_value_counts(assembly_id, attribute_name)`: exclude DELETED.
- `get_selected_attribute_value_counts(assembly_id, attribute_name)`: already filters by `SELECTED`/`CONFIRMED`, so DELETED naturally excluded — no change needed.
- `count_available_for_selection(assembly_id)`: already filters `== POOL`, so no change needed.
- `delete_all_for_assembly`: no change — this is a hard delete for the whole assembly (admin / test teardown), and at that point the assembly is gone anyway.

### 5.1 Fake repository

File: `tests/fakes.py` — `FakeRespondentRepository`.

Mirror all signature and semantic changes from the SQL implementation so the fake stays interchangeable:

- `get_by_assembly_id`: add `include_deleted: bool = False`; when False and `status is None`, filter DELETED out.
- `count_by_assembly_id`: add `include_deleted: bool = False`.
- `count_non_pool`: exclude DELETED.
- `reset_all_to_pool`: skip DELETED respondents; don't count them.
- `get_attribute_columns`: skip DELETED when picking the sample.
- `get_attribute_value_counts`: exclude DELETED.

### 5.2 Contract tests

File: `tests/contract/test_respondent_repo.py`.

Contract tests run against both the fake and the SQL repo to prove they behave identically. Add cases covering:

- `get_by_assembly_id(include_deleted=False)` hides DELETED.
- `get_by_assembly_id(include_deleted=True)` shows DELETED.
- `get_by_assembly_id(status=RespondentStatus.DELETED)` returns only DELETED (explicit status overrides the exclude).
- `count_by_assembly_id(include_deleted=False/True)` matches expectations.
- `count_non_pool` excludes DELETED.
- `reset_all_to_pool` leaves DELETED rows untouched and excludes them from the returned count.
- `get_attribute_value_counts` excludes DELETED.
- `get_attribute_columns` doesn't pick a DELETED respondent.
- Round-tripping a `Respondent` with a non-empty `comments` list preserves all fields, including `action`.

## 6 — Service layer

File: `src/opendlp/service_layer/respondent_service.py`

### 6.1 New `delete_respondent`

```python
def delete_respondent(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    respondent_id: uuid.UUID,
    comment: str,
) -> None:
    """Blank personal data on a respondent (GDPR right to be forgotten).

    Requires can_manage_assembly. A non-empty comment is required.
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="delete respondent",
                required_role="assembly-manager, global-organiser or admin",
            )

        respondent = uow.respondents.get(respondent_id)
        if not respondent or respondent.assembly_id != assembly_id:
            raise RespondentNotFoundError(
                f"Respondent {respondent_id} not found in assembly {assembly_id}"
            )
        assert isinstance(respondent, Respondent)

        respondent.delete_personal_data(author_id=user_id, comment=comment)
        uow.commit()
```

### 6.2 New `add_respondent_comment`

Split from deletion, because we want to add comments to non-deleted respondents later too (edit history). Ship it now so the mechanism is in place:

```python
def add_respondent_comment(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    respondent_id: uuid.UUID,
    text: str,
) -> None:
    """Append a comment to a respondent. Requires can_manage_assembly."""
    # same permission/lookup pattern as delete_respondent
    ...
    respondent.add_comment(text=text, author_id=user_id)
    uow.commit()
```

### 6.3 Update `get_respondents_for_assembly`

Add `include_deleted: bool = False` parameter and pass through to `uow.respondents.get_by_assembly_id`.

### 6.4 Unchanged functions

`get_respondent`, `create_respondent`, `import_respondents_from_csv`, `reset_selection_status`, `count_non_pool_respondents`, `get_respondent_attribute_columns`, `get_respondent_attribute_value_counts`, `get_selected_respondent_attribute_value_counts` — no changes.

## 7 — Flask route

File: `src/opendlp/entrypoints/blueprints/respondents.py`

Add a POST route for deletion:

```python
@respondents_bp.route(
    "/assembly/<uuid:assembly_id>/respondents/<uuid:respondent_id>/delete",
    methods=["POST"],
)
@login_required
def delete_respondent_route(
    assembly_id: uuid.UUID, respondent_id: uuid.UUID,
) -> ResponseReturnValue:
    """Blank personal data for a respondent (GDPR right to be forgotten)."""
    comment = request.form.get("comment", "").strip()
    if not comment:
        flash(_("A comment is required when deleting a respondent"), "error")
        return redirect(url_for(
            "respondents.view_respondent",
            assembly_id=assembly_id,
            respondent_id=respondent_id,
        ))
    try:
        uow = bootstrap.bootstrap()
        with uow:
            delete_respondent(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                respondent_id=respondent_id,
                comment=comment,
            )
        flash(_("Respondent personal data deleted"), "success")
        return redirect(url_for(
            "respondents.view_assembly_respondents", assembly_id=assembly_id,
        ))
    except InsufficientPermissions:
        flash(_("You don't have permission to delete respondents"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except RespondentNotFoundError:
        flash(_("Respondent not found"), "error")
        return redirect(url_for(
            "respondents.view_assembly_respondents", assembly_id=assembly_id,
        ))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.exception(
            f"Delete respondent error: assembly={assembly_id} respondent={respondent_id} user={current_user.id}: {e}"
        )
        flash(_("An error occurred while deleting the respondent"), "error")
        return redirect(url_for(
            "respondents.view_respondent",
            assembly_id=assembly_id,
            respondent_id=respondent_id,
        ))
```

(Optional, can be a follow-up) A second POST route for `add_respondent_comment`.

## 8 — Template

File: `templates/backoffice/assembly_view_respondent.html`

### 8.1 Delete action

Add to the view, only rendered when the viewer has management rights (pass a `can_manage` flag from the route, computed via the existing permission helper).

Use an Alpine.js-backed confirmation pattern consistent with the patterns page at `/backoffice/dev/patterns`. Form posts to the new delete route and includes a required textarea for the comment. Include the `X-CSRFToken` header per `docs/agent/frontend_security.md`.

Guard rails on the form:

- Disabled submit until the textarea has non-whitespace content.
- "This action is irreversible" copy in the confirmation.
- Hidden if the respondent is already DELETED.

### 8.2 Deleted banner

When `respondent.selection_status == RespondentStatus.DELETED`, show a banner at the top of the page: "Personal data for this respondent was deleted on <date> by <user>." Pull the most recent comment authored with the deletion.

### 8.3 Comments section

Render the list of comments (oldest first) with author name and timestamp. If no comments, show a placeholder row.

### 8.4 Route changes

`view_respondent` needs to:

- Compute `can_manage = can_manage_assembly(current_user, assembly)` and pass it into the template.
- Fetch author User objects for each comment (one query, batched by user id set) so the template can show names. This can be lazy — start with author_id rendered; refine with names in a follow-up if needed.

## 9 — Respondent list view

File: `templates/backoffice/assembly_respondents.html` (and any route that lists respondents)

- Respondents page: DELETED respondents are excluded by default. Leave as-is — no "show deleted" toggle for this pass.
- Historical selection CSV: unchanged (pulls from SelectionRunRecord, uses `eligible_only=False` on the adapter, gets DELETED rows with blanked values automatically).

## 10 — Tests

### 10.1 Unit tests (`tests/unit/`)

`test_respondents.py` (domain):

- `RespondentComment.to_dict` / `from_dict` round-trip.
- `add_comment` rejects empty / whitespace-only text.
- `add_comment` appends to list, sets `updated_at`.
- `delete_personal_data` blanks email, source_reference, values of all attributes (keys preserved), sets booleans to None, clears selection_run_id, sets status to DELETED, appends comment.
- `delete_personal_data` rejects empty / whitespace-only comment.
- `delete_personal_data` preserves external_id, source_type, created_at, id, assembly_id.
- `create_detached_copy` round-trips comments.
- Attribute key "comments" is rejected by `validate_no_field_name_collisions`.

`test_value_objects.py`:

- `RespondentStatus.DELETED` exists.
- `RespondentStatus.EXCLUDED` does not exist (regression guard in case something gets re-added).

### 10.2 Service layer tests

Extend `tests/unit/test_respondent_service.py` (existing file, uses `FakeUnitOfWork` — no database required):

- `delete_respondent` with assembly manager: succeeds, status becomes DELETED, comment appended with `action=RespondentAction.DELETE`.
- `delete_respondent` with confirmation-caller-only: raises `InsufficientPermissions`.
- `delete_respondent` with unrelated user: raises `InsufficientPermissions`.
- `delete_respondent` with global admin / organiser: succeeds (they have `can_manage_assembly`).
- `delete_respondent` with missing or whitespace-only comment: raises `ValueError`.
- `delete_respondent` with wrong assembly id: raises `RespondentNotFoundError`.
- `get_respondents_for_assembly` excludes DELETED by default, includes when `include_deleted=True`.
- `add_respondent_comment`: happy path + permission check.

No new test module is created; don't introduce a `tests/service_layer/` directory — service tests live in `tests/unit/` (fake-backed) or `tests/integration/` (db-backed) depending on what they exercise.

### 10.3 Repository contract tests

Covered by §5.2 above — all repo-behaviour assertions are contract tests in `tests/contract/test_respondent_repo.py`, running against both the fake and the SQL repo. The contract tests hit Postgres; any new contract tests added here will too. That's intentional — it exercises the real backend we ship on.

No separate integration-test module is needed for the filters planned in this story: the assertions (DELETED excluded by default, honoured when requested, `reset_all_to_pool` skipping DELETED, etc.) are fully covered by the contract suite running against Postgres.

### 10.4 Selection integration

Extend `tests/integration/test_sortition_data_adapter.py` and / or `tests/integration/test_sortition_db_task.py` (Postgres required — these already use the real adapter):

- Selection run with mixed POOL + DELETED respondents: DELETED never appears in selected/remaining output.
- `generate_selection_csvs`: create a respondent, select them, delete them, assert the selected CSV still contains their external_id with blanked attribute values and the right number of rows.

### 10.5 Flask route tests

Extend `tests/unit/test_respondents_routes.py` (existing file):

- POST delete as manager with comment → 302 to respondent list, flash success, DB shows DELETED.
- POST delete without comment → 302 back to respondent page, flash error, DB unchanged.
- POST delete without management rights → 302 with error flash.
- GET `view_respondent` on a DELETED row renders the deletion banner and comment list.

### 10.6 BDD (`tests/bdd/`)

Optional for this pass; add a scenario covering "Assembly manager deletes a respondent's personal data" if the BDD suite has equivalent scenarios for other respondent actions.

## 11 — Fixtures / teardown

No new tables, so `_delete_all_test_data()` in `tests/conftest.py` and `delete_all_except_standard_users()` in `tests/bdd/conftest.py` don't need new DELETE statements. Verify the existing respondents teardown still works after the migration.

Any test factories that construct `Respondent` directly need `comments=[]` passed — or a default param addition in the factory itself. Check `tests/` for factories.

## 12 — i18n

All new user-facing strings go through `_()` / `_l()`. After adding them:

```bash
just translate-regen
```

Strings added (non-exhaustive): "A comment is required when deleting a respondent", "Respondent personal data deleted", "You don't have permission to delete respondents", "Personal data for this respondent was deleted on %(date)s by %(user)s", "Delete personal data", "This action is irreversible".

## 13 — Quality gates

Before commit:

```bash
just test
just check
```

Browser smoke test of the delete flow. Use Rodney (a Playwright alternative — run `uvx rodney --help` for its capabilities) or, failing that, Playwright MCP per the frontend testing doc.

## 14 — Out of scope (follow-ups to track separately)

- Bulk deletion of respondents.
- UI for viewing / searching DELETED respondents.
- Edit history for non-deletion changes (add_comment will support this when the edit routes are built).
- Separate `respondent_comments` table — if comments balloon or we need to query them globally, we'll migrate from JSON to a table later.
- User name display in comment rendering (currently author_id is sufficient; enrich in a follow-up if needed).
- Audit log integration beyond the on-row comment list.

## 15 — Implementation todo list

Work proceeds in phases. Every phase follows red/green TDD: write failing tests first, confirm they fail for the right reason, then implement until green. Each phase ends in a committable state with `just test` and `just check` both passing.

### Phase 0 — Prep (no code change)

- [x] Run `just test` to confirm the main branch baseline is green locally.
- [x] Run `just check` to confirm linting and typing are clean.
- [x] Create a working branch.

### Phase 1 — Enum: replace `EXCLUDED` with `DELETED`

Red:

- [x] In `tests/unit/test_validators.py` or a new small test in `tests/unit/domain/`: add assertions that `RespondentStatus.DELETED` exists with value `"DELETED"` and that `EXCLUDED` no longer exists (use `hasattr` / `getattr` guard). Run; expect the "no EXCLUDED" test to still pass trivially while the "DELETED exists" test fails.

Green:

- [x] Edit `src/opendlp/domain/value_objects.py`: replace `EXCLUDED = "EXCLUDED"` with `DELETED = "DELETED"`.
- [x] Grep the repo for any stray `EXCLUDED` references and fix (expect none in live code).
- [x] Run `just test`; expect green.
- [x] Run `just check`; expect green.

### Phase 2 — `RespondentAction` enum and `RespondentComment` dataclass

Red:

- [x] In `tests/unit/domain/test_respondents.py` (create if missing — existing `tests/unit/test_respondents.py` at top level can also be extended):
  - [x] `RespondentAction` has values `NONE`, `EDIT`, `DELETE` with matching string values.
  - [x] `RespondentComment(...)` is constructible with text, author_id, created_at, and optional action (defaults to NONE).
  - [x] `to_dict` produces a dict with all four fields, `action` as the enum value string.
  - [x] `from_dict` round-trips the four-field dict.
  - [x] `from_dict` defaults `action` to `NONE` when the key is absent (legacy-row guard).
  - [x] Instances are frozen (attempting to mutate raises).
- [x] Run tests; expect import errors until the types exist.

Green:

- [x] Add `RespondentAction` enum to `src/opendlp/domain/value_objects.py`.
- [x] Add `RespondentComment` dataclass to `src/opendlp/domain/respondents.py`.
- [x] Rerun; expect green.

### Phase 3 — Respondent domain: `comments` field + `add_comment` + `delete_personal_data`

Red (in `tests/unit/test_respondents.py`):

- [x] Respondent constructor accepts `comments=[...]` and defaults to `[]`.
- [x] An attribute key normalising to `"comments"` is rejected by `validate_no_field_name_collisions`.
- [x] `add_comment` appends a `RespondentComment` with `action=NONE` by default and `action=EDIT`/`DELETE` when passed.
- [x] `add_comment` rejects empty and whitespace-only text with `ValueError`.
- [x] `add_comment` updates `updated_at`.
- [x] `delete_personal_data` sets status to `DELETED`, blanks `email` / `source_reference`, zeroes booleans to `None`, clears `selection_run_id`, blanks all attribute *values* to `""` while preserving *keys*, and appends a comment with `action=DELETE`.
- [x] `delete_personal_data` preserves `id`, `external_id`, `assembly_id`, `source_type`, `created_at`, and any prior comments.
- [x] `delete_personal_data` rejects empty / whitespace-only comment with `ValueError`.
- [x] `create_detached_copy` round-trips a non-empty `comments` list (list is copied, not shared).
- Run tests; expect failures for all new assertions.

Green:

- [x] Add `"comments"` to `_RESERVED_FIELD_NAMES` in `respondents.py`.
- [x] Extend `Respondent.__init__` to accept and store `comments`.
- [x] Implement `add_comment` and `delete_personal_data` per §2.5.
- [x] Update `create_detached_copy`.
- [x] Rerun; expect green.
- [x] Run `just check`; fix any typing issues on the new dataclass / list fields.

### Phase 4 — ORM column + `TypeDecorator` + migration

Red:

- [x] Add a contract-test case in `tests/contract/test_respondent_repo.py` asserting that a respondent with a non-empty `comments` list round-trips through the repository (save, fetch, assert comment text / action / author_id / created_at all match). Run against Postgres; expect failure because the column doesn't exist.

Green:

- [x] In `src/opendlp/adapters/orm.py`: add `RespondentCommentListJSON` `TypeDecorator` that serialises `list[RespondentComment]` via `to_dict` / `from_dict`.
- [x] Add `comments` column to the `respondents` table using the new decorator, `nullable=False, default=list`.
- [x] Generate migration: `uv run alembic revision --autogenerate -m "add comments to respondents"`.
- [x] Edit the migration to include `server_default='[]'` so existing rows backfill, then drop the server default in the same migration or a follow-up if we don't want it long-term.
- [x] Apply migration to the local test DB and rerun the contract test; expect green.
- [x] Run full `just test`; expect green.
- [x] Run `just check`.

### Phase 5 — Repo behaviour: `include_deleted` filter + DELETED-aware counts

Red (in `tests/contract/test_respondent_repo.py`):

- [x] `get_by_assembly_id()` (no args) excludes DELETED respondents.
- [x] `get_by_assembly_id(include_deleted=True)` includes DELETED respondents.
- [x] `get_by_assembly_id(status=RespondentStatus.DELETED)` returns only DELETED respondents (explicit status overrides the exclude).
- [x] `count_by_assembly_id()` excludes DELETED; `count_by_assembly_id(include_deleted=True)` includes them.
- [x] `count_non_pool` excludes DELETED.
- [x] `reset_all_to_pool` does not change DELETED rows and doesn't count them in its return value.
- [x] `get_attribute_columns` picks a live (non-DELETED) respondent as the sample.
- [x] `get_attribute_value_counts` excludes DELETED.
- [x] `count_available_for_selection` excludes DELETED (regression guard — already filters by `POOL`).
- Run; expect failures for all except the last.

Green:

- [x] Update `RespondentRepository` abstract interface in `src/opendlp/service_layer/repositories.py` with the new `include_deleted` params.
- [x] Update `SqlAlchemyRespondentRepository` in `src/opendlp/adapters/sql_repository.py` per §5.
- [x] Update `FakeRespondentRepository` in `tests/fakes.py` per §5.1.
- [x] Rerun contract tests; expect green for both SQL and fake fixtures.
- [x] Run `just test`; fix any unrelated callers that need to opt in via `include_deleted=True`.
- [x] Run `just check`.

### Phase 6 — Service layer: `delete_respondent` and `add_respondent_comment`

Red (in `tests/unit/test_respondent_service.py`):

- [x] `delete_respondent` as assembly manager: sets status DELETED, appends a DELETE comment authored by the caller.
- [x] `delete_respondent` as global admin: succeeds (they have `can_manage_assembly`).
- [x] `delete_respondent` as global organiser: succeeds.
- [x] `delete_respondent` as confirmation caller: raises `InsufficientPermissions`.
- [x] `delete_respondent` as unrelated user: raises `InsufficientPermissions`.
- [x] `delete_respondent` with empty / whitespace-only comment: raises `ValueError`.
- [x] `delete_respondent` with respondent belonging to a different assembly: raises `RespondentNotFoundError`.
- [x] `delete_respondent` with non-existent respondent id: raises `RespondentNotFoundError`.
- [x] `delete_respondent` with non-existent user: raises `UserNotFoundError`.
- [x] `delete_respondent` with non-existent assembly: raises `AssemblyNotFoundError`.
- [x] `add_respondent_comment` as manager: appends a `NONE`-action comment.
- [x] `add_respondent_comment` as confirmation caller: raises `InsufficientPermissions`.
- [x] `add_respondent_comment` with empty text: raises `ValueError`.
- [x] `get_respondents_for_assembly()` excludes DELETED by default.
- [x] `get_respondents_for_assembly(include_deleted=True)` includes DELETED.
- Run; expect failures / import errors.

Green:

- [x] Implement `delete_respondent` per §6.1.
- [x] Implement `add_respondent_comment` per §6.2.
- [x] Extend `get_respondents_for_assembly` with `include_deleted` passthrough.
- [x] Rerun; expect green.
- [x] Run `just check`.

### Phase 7 — Sortition integration

Red (in `tests/integration/test_sortition_data_adapter.py` and/or `test_sortition_db_task.py`; Postgres required):

- [x] Selection run on a mix of POOL + DELETED respondents: DELETED external_ids never appear in selected or remaining results.
- [x] `generate_selection_csvs`: select a respondent, delete them, regenerate the CSV — the selected CSV still contains their external_id; attribute columns are present but values are blank; row count equals the original `selected_ids` length.
- Run; expect green already (sortition adapter is unchanged). The value of these tests is regression protection.

Green:

- [x] No code change expected. If a test fails, diagnose before adjusting the adapter — the plan's design is that no adapter change is needed. **Revised:** the CSV generator needed a small change (`_person_list_to_table_with_deleted`) because the sortition library's validator rejects blanked rows. DELETED respondents are detected in `generate_selection_csvs` and synthesised into the output table with a `"DATA DELETED"` placeholder.
- [x] Run `just test`; expect green.
- [x] Run `just check`.

### Phase 8 — Flask route: POST delete

Red (in `tests/e2e/test_backoffice_respondents.py` — uses existing Postgres and auth fixtures):

- [x] POST to the delete route as admin with a comment → 302 to respondent list, DB row is DELETED, comment recorded.
- [x] POST without a comment → 302 back to the respondent page, error flash, DB unchanged.
- [x] POST without login → redirected to login.
- [x] POST for a respondent in a different assembly → redirected with "respondent not found" flash.
- Run; expect 404 on the route.

Green:

- [x] Add the `delete_respondent_route` per §7 in `src/opendlp/entrypoints/blueprints/respondents.py`.
- [x] Rerun; expect green.
- [x] Fix in-place-mutation bug on `Respondent.comments` — SQLAlchemy's JSON column change-detection needs a reassigned list, not `.append()`.
- [x] Run `just check`.

### Phase 9 — Template: delete form, deleted banner, comment list

Red (in `tests/e2e/test_backoffice_respondents.py`):

- [x] `view_respondent` passes `can_manage` to the template; the delete form is rendered for managers.
- [x] `view_respondent` for a DELETED row renders the "Personal data deleted" banner with the deletion author and timestamp.
- [x] `view_respondent` renders the comment list with text, author, action, and timestamp.
- [x] The delete form post target matches `url_for("respondents.delete_respondent_route", ...)` and includes the CSRF token.
- Run; expect failures.

Green:

- [x] Extend the `view_respondent` route to compute `can_manage_assembly` and pass it + the comment authors into the template.
- [x] Update `templates/backoffice/assembly_view_respondent.html` per §8: delete section (CSP-compatible Alpine.js toggle form), deletion banner, comment list.
- [x] Rerun; expect green.
- [ ] Browser smoke of the delete flow using Rodney (fallback: Playwright MCP):
  - [ ] Delete a respondent, confirm UI shows the banner.
  - [ ] Non-manager user cannot see the delete form.
  - [ ] Submitting without a comment shows the error and keeps the record intact.

### Phase 10 — BDD (optional for this story)

- [ ] If there are existing BDD scenarios for respondent actions, add one covering "Assembly manager deletes a respondent's personal data". **Skipped:** coverage at the service / route / template level is comprehensive; no existing BDD scenario exercises the view_respondent page, so adding one is out of scope for this PR.
- [x] Confirm `delete_all_except_standard_users()` in `tests/bdd/conftest.py` still cleans respondents correctly (no new table, so expected to be a no-op verification).
- [x] Run `CI=true uv run pytest tests/bdd/` for any new or touched scenarios. **N/A** — no new scenarios.

### Phase 11 — i18n, final quality gates, commit

- [ ] `just translate-regen` to pick up new strings.
- [ ] Inspect translation files for the new entries and note any follow-up translation work.
- [ ] `just test` (full suite) — green.
- [ ] `just check` — green.
- [ ] Self-review diff against §1–§14 of this plan; ensure nothing drifted.
- [ ] Squash / organise commits for review; each phase should be a discrete commit with a message referencing its phase.
- [ ] Open PR against main; link this plan document.
