# Broad e2e conversion — per-file review & recommendations

> Status: **Review complete; no code changed yet.** This document reviews every
> file in `tests/e2e/` and classifies each test for the broad e2e conversion that
> follows the Phase 1/2/3 work in [`plan.md`](plan.md) and [`phase-3.md`](phase-3.md).
> Phases 1–3 are done: the `get_flask_uow()` seam, the shared-store
> `FakeUnitOfWork`/`FakeStore`, the `tests/component/` tier (cachelib sessions, no
> PostgreSQL/Redis), the `requires_*`/`db_semantics` markers, and the placement
> guard all exist. This is the deferred "broad rollout" step.

## 0. Implementation checklist

Tick each file as its conversion lands (component file written, e2e trimmed to
smokes + `db_semantics`, `just check` green, committed).

**Phase 1 — clean, no-blocker files**
- [x] `test_profile_management.py`
- [x] `test_assembly_crud.py`
- [x] `test_backoffice_general.py`
- [x] `test_2fa_flow.py`
- [x] `test_resend_confirmation.py`

**Phase 2 — auth + admin (with db_semantics carve-outs)**
- [x] `test_auth_flow.py`
- [x] `test_admin_invite_management.py`
- [x] `test_admin_user_management.py`

**Phase 3 — assembly + respondents + targets**
- [x] `test_backoffice_assembly.py`
- [x] `test_assembly_gsheet_crud.py`
- [x] `test_assembly_user_management.py`
- [x] `test_backoffice_respondents.py`
- [x] `test_backoffice_respondent_field_schema.py`
- [x] `test_targets_pages.py`

**Phase 4 — selection/gsheet non-Celery slices**
- [x] `test_sortition_routes.py`
- [x] `test_db_selection_routes.py`
- [x] `test_db_selection_backoffice.py`
- [x] `test_backoffice_gsheet_selection.py`
- [x] `test_gsheets_routes.py`

**Phase 5 — mark-only (db_semantics, no move)**
- [x] `test_health_check_monitoring.py` (8 selection-run tests marked `db_semantics`)
- [x] `test_oauth_flow.py` (moved 15 non-provider tests via an OAuth-enabled component app; provider-callback tests stay e2e)

**Phase 6 — leave as-is (no action)**
- [x] `test_registration_public.py`, `test_registration_image_serve.py`,
  `test_registration_auto_reply.py` (already trimmed in Phase 3 of `phase-3.md`)
- [x] `test_health_check.py`, `test_feature_flags_e2e.py`, `test_wellknown.py`

**Phase 7 — legacy (no migration; trim/delete with blueprint)**
- [x] `test_targets_legacy_pages.py` (intentionally left untouched — behavioural coverage of a still-live blueprint; delete with the blueprint)
- [x] `test_respondents_pages.py` (intentionally left untouched — same rationale)

## 1. The rule we are applying

For each Flask route:

- **Keep 1–3 PostgreSQL happy-path smoke tests in `tests/e2e/`** (`KEEP-SMOKE`).
- **Move the richer behavioural coverage to `tests/component/`** (`MOVE-COMPONENT`)
  — validation errors, permission/redirect branches, not-found, form re-render,
  state changes — run against a `FakeUnitOfWork`, asserting on the `FakeStore`
  and the rendered response (state-based, never `mock.assert_called_with`).
- **Keep in `tests/e2e/` with `@pytest.mark.db_semantics`** the tests whose value
  *is* real database behaviour (`KEEP-DB-SEMANTICS`) — repository
  ordering/pagination/search/filter that the fake reimplements in Python, JSON
  column round-trips, real timestamp/age queries, cross-request persistence whose
  fidelity is the point.
- **Keep in `tests/e2e/` for a non-DB reason** (`KEEP-E2E-OTHER`) — Celery
  dispatch/poll/revoke, OAuth provider flows, real CSRF/CSP-nonce, health/infra
  probes, real Redis rate-limiting.

## 2. Headline numbers

~870 e2e tests across 30 files. Aggregate of the per-file reviews below:

| Bucket | Approx. count | What happens to them |
| --- | --- | --- |
| `MOVE-COMPONENT` | ~480 | Net-new/expanded `tests/component/` files; drop CSRF token, login via `session_transaction`, assert on `FakeStore`. |
| `KEEP-SMOKE` | ~90 | Stay in `tests/e2e/` as the thin per-route PG happy-path. |
| `KEEP-E2E-OTHER` | ~90 | Stay e2e: ~70 Celery-tail (candidate once the deferred Celery seam exists), ~15 OAuth, a handful CSP/CSRF/Redis/email-boundary, all infra probes. |
| `KEEP-DB-SEMANTICS` | ~30 | Stay e2e, newly marked `db_semantics`. |
| `LEAVE / DELETE` | ~31 | The legacy targets file — delete with its blueprint. |

The big win is the ~480 component conversions (no PostgreSQL, no Redis). The
Celery-tail (~70) cannot move until the deferred Celery-boundary seam (phase-3
§6.4) is built — they are flagged `candidate-once-celery-seam-exists` throughout.

## 3. Cross-cutting findings (read before starting any file)

1. **CSRF is already disabled in the e2e config.** `FlaskTestConfig.WTF_CSRF_ENABLED
   = False` and `tests/e2e/helpers.get_csrf_token` returns the literal
   `"csrf_token_placeholder"`. So the many `test_*_requires_csrf_token` tests are
   **misnamed** — they assert the no-data redirect branch, which the component tier
   reproduces identically. They are **not** `KEEP-E2E-OTHER`. The only genuine
   real-CSRF tests are in `test_registration_public.py` (which flips
   `WTF_CSRF_ENABLED=True`) and one latent no-op in `test_auth_flow.py`
   (`test_csrf_protection_enabled` currently asserts nothing — fix when touched).

2. **The Celery tail is a `.delay`/`.apply_async`/`control.revoke` boundary, not the
   whole route.** In the selection/gsheet files only ~19 tests (sortition_routes,
   db_selection_routes, db_selection_backoffice) plus the two gsheet files'
   dispatch/status-poll tests genuinely need Celery. The surrounding
   auth/authz/validation/render/redirect tests on the same routes move to component
   now. Note: the DB-selection files patch **internal sortition-algorithms boundary
   functions** (`check_db_selection_data`, `generate_selection_csvs`) — those are
   legit boundary stubs and are component-compatible; only
   `start_db_select_task`/`cancel_task`/`run_select*.delay`/`control.revoke` are the
   true Celery tail.

3. **The `db_semantics` clusters are specific and small.** They concentrate on a few
   fake repository methods that reimplement SQL in Python:
   - `FakeUserRepository.filter_paginated` / `search_users_not_in_assembly`
     (ILIKE/ORDER BY/LIMIT, email-priority sort, AND/OR fragment matching) —
     admin user list, assembly member search (both legacy and backoffice).
   - Respondent attribute aggregation: `get_attribute_columns`,
     `get_attribute_value_counts`, `get_selected_attribute_value_counts`,
     `count_available_for_selection`, `get_by_assembly_id_paginated` — targets
     check/add-from-columns, respondents pagination.
   - JSON-column round-trips: `SelectionSettings` (gsheet edit), choice-field
     `options`, target category `values`.
   - `selection_run_records` latest-by-`created_at`/task-type/age queries —
     monitoring health endpoint.
   - Field-schema `sort_order` reorder.

4. **Two seams gate conversions beyond Celery.** OAuth needs a fake app with OAuth
   client IDs configured **plus** a provider mock — neither exists in the component
   tier yet. The ~13 non-provider OAuth tests (remove-method, profile display,
   login-required redirects) are `candidate-once-oauth-fake-app-exists`; the
   provider-callback half stays e2e indefinitely.

5. **Login mechanism differs by tier.** e2e logs in via real `POST /auth/login`
   (password hashing/verify); the component conftest uses `session_transaction`
   direct login. Converting drops the password round-trip — fine, since none of
   these tests are about authentication itself. Tests already using
   `session_transaction` (profile, oauth state tests) port most cleanly.

6. **Email-adapter `caplog` tests are boundary tests.** A few management tests assert
   the console email adapter logged a send. Left as `KEEP-E2E-OTHER` to preserve the
   boundary assertion; they could move to component with the adapter spied.

7. **Two distinct respondents blueprints and two targets blueprints.**
   `/backoffice/assembly/<id>/respondents` (rich, current) vs
   `/assemblies/<id>/respondents` (older); `targets_bp` (current,
   `/backoffice/...`) vs `targets_legacy_bp` (`/assemblies/.../targets`, slated for
   deletion). Do not dedupe smokes across them. **Resolved (Doctor Chewie):** the
   `/assemblies/<id>/respondents` blueprint (`test_respondents_pages.py`) **is** also
   destined for legacy retirement. So it is treated like `test_targets_legacy_pages.py`:
   do not migrate it to component; leave/trim it for deletion with its blueprint.

---

## 4. Per-file detail

### Group: auth / users / profile / 2FA / OAuth

#### test_auth_flow.py
Routes: register, login, logout, dashboard, root, confirm-email. ~32 tests.

| Test (or group) | Bucket | Reason |
|---|---|---|
| `test_register_with_valid_invite_success` | KEEP-SMOKE | register PG smoke |
| 5 register validation/branch variants (expired/invalid invite, missing fields, mismatch, duplicate email) | MOVE-COMPONENT | form re-render error branches |
| `test_login_success` | KEEP-SMOKE | login PG smoke |
| `test_login_invalid_credentials_fails`, `_nonexistent_user_fails`, `_remember_me_functionality` | MOVE-COMPONENT | auth-failure + Flask-Login cookie behaviour |
| `test_logout_success` | KEEP-SMOKE | logout smoke |
| dashboard/protected/session-persistence/root-redirect/login-required (~7) | MOVE-COMPONENT | auth-decorator + render branches |
| `test_registration_with_invite_code_in_url` | MOVE-COMPONENT | form pre-fill render |
| 5 `test_login_rate_limiting_*` | KEEP-E2E-OTHER | **real Redis rate-limiting** — the limiter is Redis-backed, distinct from the cachelib session the component tier uses |
| `test_csrf_protection_enabled` | KEEP-E2E-OTHER | real CSRF (and currently asserts nothing — fix it) |
| 2 cache-header tests | MOVE-COMPONENT | Cache-Control middleware on auth state |
| `test_confirm_email_post_confirms_and_redirects` | KEEP-SMOKE | confirm-email POST smoke |
| 5 confirm-email GET/invalid/expired branches | MOVE-COMPONENT | token-state set on fake domain objects directly |

**Recommendation:** 4 smokes, ~22 component, 0 db_semantics, 6 e2e-other (5 Redis rate-limit + 1 CSRF).

#### test_admin_user_management.py
Routes: `/admin/users` list/filter/search/paginate, view, edit. ~21 tests.

| Test (or group) | Bucket | Reason |
|---|---|---|
| `test_list_users_page_accessible_to_admin` | KEEP-SMOKE | list PG smoke |
| permission/redirect branches (2) | MOVE-COMPONENT | 403 / login redirect |
| `test_list_users_shows_pagination` | KEEP-DB-SEMANTICS | `filter_paginated` LIMIT/OFFSET+ordering |
| filter by role / active status (2) | KEEP-DB-SEMANTICS | `filter_paginated` filtering |
| `test_list_users_search_by_name` | KEEP-DB-SEMANTICS | ILIKE vs Python `in` substring |
| view page (2 — keep 1) | KEEP-SMOKE / MOVE-COMPONENT | one view smoke, dup moves |
| edit form render, role pre-select, self-protection, role/deactivate changes, nav-by-role (~10) | MOVE-COMPONENT | request→service→form |
| `test_edit_user_name_success` | KEEP-SMOKE | edit POST smoke (real cross-request persistence) |

**Recommendation:** 3 smokes, ~12 component, 4 db_semantics, 0 e2e-other. This file is the canonical `filter_paginated`/`search` divergence risk.

#### test_admin_invite_management.py
Routes: invites list, create, view, revoke, cleanup. ~21–26 tests.

| Test (or group) | Bucket | Reason |
|---|---|---|
| list accessible, view accessible, create success, revoke success | KEEP-SMOKE | one smoke per route |
| 403/redirect/not-found branches (~6) | MOVE-COMPONENT | permission/auth/not-found |
| list rendering of stats/codes/email/role tags (4) | MOVE-COMPONENT | seed via `generate_invite`, render asserts |
| create role/expiry variants (2, `time_machine`) | MOVE-COMPONENT | domain expiry logic, not DB |
| view detail variants (3) | MOVE-COMPONENT | render |
| cleanup success/no-expired/preserves-active (3) | MOVE-COMPONENT | `get_expired_invites`/delete over fake |
| `test_create_invite_with_email` | KEEP-E2E-OTHER | email-adapter `caplog` boundary |

**Recommendation:** 4–5 smokes, ~14 component, 0 db_semantics, 1 e2e-other (email).

#### test_profile_management.py
Routes: profile view, edit, change-password, set-password, remove-oauth. ~17 tests.

| Test (or group) | Bucket | Reason |
|---|---|---|
| `test_view_own_profile`, `test_edit_profile_post_success`, `test_change_password_success`, `test_oauth_user_can_set_password` | KEEP-SMOKE | one smoke per route (change-password re-logs in → real persistence) |
| login-required redirects, GET form renders, validation branches, oauth-redirect branch, remove-oauth multi-step (~13) | MOVE-COMPONENT | all request→service→form; oauth fixtures already use `session_transaction` |

**Recommendation:** 4 smokes, ~13 component, 0 db_semantics, 0 e2e-other. Cleanest file in the batch.

#### test_2fa_flow.py
Routes: 2fa view/setup/enable, login verify-2fa, regenerate backup codes, disable. ~8 tests.

| Test (or group) | Bucket | Reason |
|---|---|---|
| `test_setup_2fa_complete_flow` | KEEP-SMOKE | full setup journey (real TOTP/crypto in-process) |
| `test_login_with_2fa_totp_code` | KEEP-SMOKE | two-step login smoke |
| `test_disable_2fa` | KEEP-SMOKE | disable smoke |
| invalid-code, backup-code, invalid login, regenerate (4) | MOVE-COMPONENT | branches over fake repos |

**Recommendation:** 3 smokes, 4 component, 0 db_semantics, 0 e2e-other. Component conftest must set `TOTP_ENCRYPTION_KEY` (via `temp_env_vars`); pyotp/crypto run in-process — no boundary mock. TOTP rate-limiting is DB-row-counted (fake counts in Python — acceptable).

#### test_oauth_flow.py
Routes: OAuth register/login/callback (google+microsoft), profile link/unlink, remove-password/oauth, profile display. ~28 tests.

| Test (or group) | Bucket | Reason |
|---|---|---|
| every test driving the mocked OAuth provider callback/redirect: register-via-OAuth ×2, login-via-OAuth ×2, auto-link, link-success ×2, replace-provider, email-mismatch, 2× `initiates_oauth_flow`, register-without-invite ×2 (~13–15) | KEEP-E2E-OTHER | OAuth provider boundary; app fixture is OAuth-custom. `candidate-once-oauth-fake-app-exists` |
| OAuth-register GET form render ×2, invalid-invite POST validation | MOVE-COMPONENT | no provider call reached |
| remove-password/remove-oauth state changes (5), profile display by auth method (4), login-required redirects (3) | MOVE-COMPONENT | no provider call — pure POST→service→re-read |

**Recommendation:** ~13–15 e2e-other (the OAuth happy-paths *are* the smokes), ~13 component (gated on an OAuth-enabled component app fixture), 0 db_semantics. The provider-callback half stays e2e indefinitely.

---

### Group: assembly

#### test_assembly_crud.py  *(the Phase 2 pilot — bodies already proven on fakes)*
Routes: dashboard list, new, view, edit. ~22 tests.

| Test (or group) | Bucket | Reason |
|---|---|---|
| `test_assemblies_list_empty_state`, `test_create_assembly_success`, `test_edit_assembly_success`, `test_complete_create_view_edit_workflow` | KEEP-SMOKE | list + create + edit + full round-trip |
| list rendering/role-button/permission variants, create form/validation/minimal/permission/auth, view success/fields/not-found/auth, edit form/validation/not-found/permission/auth, breadcrumbs, appears-in-list (~18) | MOVE-COMPONENT | pilot-proven; promote `test_view_assembly_success` if a view smoke is wanted |

**Recommendation:** 4 smokes, ~18 component, 0 db_semantics, 0 e2e-other.

#### test_assembly_gsheet_crud.py
Routes: `GET/POST /assemblies/<id>/gsheet` (create+edit share one route), delete. ~28 tests. The route writes both `AssemblyGSheet` and the assembly's `SelectionSettings` (JSON-ish column) with team-default expansion.

| Test (or group) | Bucket | Reason |
|---|---|---|
| `test_create_gsheet_success`, `test_delete_gsheet_success`, `test_complete_create_edit_delete_workflow` | KEEP-SMOKE | create + delete + round-trip |
| `test_edit_gsheet_get_form_populates_selection_settings_fields`, `test_edit_gsheet_success_with_team_eu`, `_with_team_custom` | KEEP-DB-SEMANTICS | re-read PG to assert `SelectionSettings` round-trip + team-default expansion |
| form renders, URL/required validation matrix, custom-team create, permission/auth/not-found, state transitions, breadcrumbs, hard/soft validation branches (~22) | MOVE-COMPONENT | validation + render; happy outcomes don't read PG back |

**Recommendation:** 3 smokes, ~22 component, 3 db_semantics, 0 e2e-other.

#### test_assembly_user_management.py  *(legacy `/assemblies/...` member routes)*
Routes: members GET/POST, member remove, search-users. ~22 tests.

| Test (or group) | Bucket | Reason |
|---|---|---|
| `test_add_user_to_assembly_success`, `test_remove_user_from_assembly_success` | KEEP-SMOKE | add + remove smoke |
| 4 search-match tests (`returns_matching`, `case_insensitive`, `by_email`, `by_last_name`) + `excludes_users_already_in_assembly` | KEEP-DB-SEMANTICS | `search_users_not_in_assembly` ordering/fragment matching |
| `test_add_user_to_assembly_sends_notification_email` | KEEP-E2E-OTHER | email-adapter `caplog` |
| role-picker render, role variants, flash branches, invalid-id, `requires_csrf` (CSRF disabled→redirect branch), empty/no-match search, permission branches (~14) | MOVE-COMPONENT | request→service; assert via permission helpers on fake |

**Recommendation:** 2 smokes, ~14 component, 5 db_semantics, 1 e2e-other.

#### test_backoffice_assembly.py
Routes: detail, new, edit, members page, members search, member add/remove, QR-code PNG, targets upload, delete-targets, view targets, view data. ~39–50 tests.

| Test (or group) | Bucket | Reason |
|---|---|---|
| create success, edit success, full workflow, member add, member remove, targets-CSV upload, delete-targets, (+ one detail render) | KEEP-SMOKE | one smoke per route (~8) |
| 4 member-search-match + exclusion + dup case-insensitive | KEEP-DB-SEMANTICS | `search_users_not_in_assembly` |
| `test_registration_url_copy_widget_uses_csp_safe_data_attributes` | KEEP-E2E-OTHER | CSP-safe rendering invariant |
| `test_registration_qr_code_endpoint_returns_png` | KEEP-E2E-OTHER | real PNG bytes (qrcode is pure-Python → component-eligible if desired) |
| `test_add_user_sends_notification_email` | KEEP-E2E-OTHER | email `caplog` |
| detail dup, auth/not-found/permission branches, create variants/validation, edit form/validation, members render, JSON-shape, flash branches, empty search, targets upload flash/error branches, form-field-name regression, view-targets render (~22) | MOVE-COMPONENT | render + validation + branches |

**Recommendation:** ~8 smokes, ~22 component, 6 db_semantics, 3 e2e-other.

#### test_backoffice_general.py
Routes: backoffice dashboard, showcase, search-demo, assembly data page. 18 tests.

| Test (or group) | Bucket | Reason |
|---|---|---|
| `test_dashboard_loads_for_logged_in_user`, `test_view_assembly_data_page_loads` | KEEP-SMOKE | dashboard + data-page smoke |
| dashboard auth/role/assemblies render, showcase render, search-demo (static mock data — no store!), data-page source-param branches, auth/not-found, data-source-lock UI (~16) | MOVE-COMPONENT | conditional render driven by gsheet config presence/absence |

**Recommendation:** 2 smokes, 16 component, 0 db_semantics, 0 e2e-other.

---

### Group: respondents / targets

#### test_backoffice_respondents.py
Routes: upload-respondents, confirm-diff (GET/POST), delete-respondents, list, single, delete, transition-status, edit. ~42 tests. **CSV import is inline (no Celery).**

| Test (or group) | Bucket | Reason |
|---|---|---|
| upload-with-id-column, delete-respondents, list-with-csv-source, view-respondent, delete-with-comment, transition-status POST, edit POST | KEEP-SMOKE | one smoke per route (~7) |
| `test_oversized_upload_is_rejected_with_friendly_error` | KEEP-E2E-OTHER | request-size limit boundary (monkeypatches `get_max_csv_upload_bytes`) |
| upload branches, list render variants, view name-derivation/grouping/not-found, deletion UI states, transition button-render/validation, edit form/validation/refusal branches (~32) | MOVE-COMPONENT | inline import → state assertions |
| 4 Redis-backed diff tests (re-upload-added-column, diff-page-shows, cancel-discards, confirm-after-expiry) + 1 smoke | KEEP-E2E-OTHER (redis) | **Correction:** the pending-upload diff stash is **Redis-backed** (`service_layer/csv_upload_stash.py`), not cachelib — so these stay e2e (`requires_redis`); only the 2 genuinely-inline diff tests moved to component |

**Recommendation:** ~7 smokes, ~34 component, 0 db_semantics, 1 e2e-other.

#### test_backoffice_respondent_field_schema.py
Routes: schema page, initialise, field update/move/add/delete, guess-types, option add/remove/update, fields-tab link. ~34 tests. Seeded inline via CSV import / schema service.

| Test (or group) | Bucket | Reason |
|---|---|---|
| schema render (populated), initialise, update label/group, add field, delete non-fixed, add-option (JSON round-trip), guess-types POST | KEEP-SMOKE | one smoke per route (~7) |
| `TestMoveField::move_up_swaps_with_previous` | KEEP-DB-SEMANTICS | `sort_order` reorder / `list_by_assembly` ordering |
| empty-state/auth, on-registration-page branch, choice-seed/duplicate/empty-key validation, form render, delete-fixed refusal, fields-tab links, field-type transitions, option CRUD variants, guess-button visibility (~26) | MOVE-COMPONENT | service-enforced (duplicate key is service logic, not DB constraint) |

**Recommendation:** ~7 smokes, ~26 component, 1–2 db_semantics, 0 e2e-other. Optionally mark the kept `add-option` smoke `db_semantics` to pin the JSON options serialization.

#### test_respondents_pages.py  *(older `/assemblies/<id>/respondents` blueprint — legacy, slated for deletion)*
Routes: respondents page, upload, reset-status. 19 tests.

**Resolved (cross-cut #7):** this blueprint is destined for legacy retirement, so it is
treated like `test_targets_legacy_pages.py`. **Migrate nothing.** Leave untouched until the
blueprint is deleted, or trim now to 2–3 PG smokes and drop the rest. Delete the whole file
with the blueprint.

#### test_targets_legacy_pages.py  *(legacy blueprint — slated for deletion)*
~33 tests on `targets_legacy_bp` (`/assemblies/<id>/targets...`).

**Recommendation:** **Migrate nothing.** Do not author component tests for a doomed blueprint. Either leave untouched until the blueprint is deleted, or trim now to 2 PG smokes (page render + valid CSV upload) and drop the other ~31. Delete the whole file with the blueprint.

#### test_targets_pages.py  *(current `targets_bp`, `/backoffice/...`)*
Routes: page, upload, category add/rename/delete, value add/edit/delete, add-missing-values, add-from-columns, check. Many routes have a normal + HTMX-fragment pair. ~33 tests. Inline import.

| Test (or group) | Bucket | Reason |
|---|---|---|
| page-with-data, upload, add-category, delete-category, add-value, edit-value, delete-value, rename-category, add-missing-values | KEEP-SMOKE | one smoke per route (~9) |
| `TestAddCategoriesFromColumns::creates_categories_from_selected_columns` | KEEP-DB-SEMANTICS | `get_attribute_columns`/value-counts over respondent JSON (DISTINCT/jsonb) |
| `TestCheckTargets::test_check_with_valid_data_shows_success` | KEEP-DB-SEMANTICS | real attribute counting vs targets (`count_available_for_selection`) |
| all HTMX-fragment variants, validation branches, auth/empty-state/not-found, viewer-permissions, button-visibility, single-column/no-columns/no-values branches (~20) | MOVE-COMPONENT | render + validation |

**Recommendation:** ~9 smokes, ~20 component, 2 db_semantics, 0 e2e-other.

---

### Group: selection / Celery-dominated

#### test_sortition_routes.py
Routes: gsheet select/load/replace/manage-tabs (+ progress/cancel), run view, assembly data. ~70 tests. Celery today: per-test `@patch` of `...sortition.tasks.{load_gsheet,run_select,manage_old_tabs}.{delay,apply_async}` and `...sortition.app.app.control.revoke`.

| Test (or group) | Bucket | Reason |
|---|---|---|
| 7 dispatch tests (load/select/test-select/replace×2/list-tabs/delete-tabs) + manager-can-start | KEEP-E2E-OTHER (celery) | `.delay`/`.apply_async`; candidate-once-celery-seam-exists |
| 3 cancel tests (`control.revoke`) | KEEP-E2E-OTHER (celery) | revoke is control, not dispatch; keep ~1 as cancel smoke |
| select/replace/manage-tabs GET render (3), progress fragment (1), `/data` history (1) | KEEP-SMOKE | per-route happy-path smoke |
| `test_view_assembly_data_pagination_works` | KEEP-DB-SEMANTICS | 55-row `created_at desc` ordering/pagination |
| ~13 requires-auth, ~10 requires-permission, 404/cross-assembly validation (~10), missing-gsheet/number validation (~5), progress fragments (~8), status-page renders (3), run-redirect routing (3+1), cancel-already-completed, cancel render (2), history render (2) (~55) | MOVE-COMPONENT | auth/authz/validation/render/redirect — `SelectionRunRecord` seeded into `FakeStore` |

**Recommendation:** ~4 smokes, ~55 component, 1 db_semantics, ~10 e2e-celery. Only ~10 of 70 are genuinely Celery-bound.

#### test_db_selection_routes.py  *(legacy `db_selection_legacy`)*
Routes: page, run, check, progress, cancel, settings GET/POST, db_replace, downloads, reset-respondents, run view, respondents filter. ~55 tests. Celery: `@patch("...run_select_from_db.delay")`, `@patch("...app.app.control.revoke")`. Internal `check_db_selection_data` / `generate_selection_csvs` patches are **sortition-algorithms boundary stubs, not Celery**.

| Test (or group) | Bucket | Reason |
|---|---|---|
| start-selection ×2, start error, cancel | KEEP-E2E-OTHER (celery) | `.delay` + `revoke`; candidate-once-celery-seam-exists |
| page load, settings GET, settings POST persist, check, progress/download | KEEP-SMOKE | per-route smoke |
| check success/failure/error/guard (boundary-stub), progress fragments, settings validation matrix, column-render, downloads + error variants (boundary-stub), 404/cross-assembly, pre-dispatch guards, readiness warnings (6), non-pool warnings (5), reset (3), status-filter (3) (~46) | MOVE-COMPONENT | request→service over fake; boundary stubs usable in component |

**Recommendation:** ~5 smokes, ~46 component, 0 db_semantics, ~4 e2e-celery. ~50 of 55 convertible now.

#### test_db_selection_backoffice.py  *(`db_selection_backoffice`)*
Routes: check, run, modal-progress, cancel, downloads (selected/remaining/report), reset, csv settings, selection page. ~42 tests. **Real CSRF used throughout** (`get_csrf_token` + `csrf_token` in POST). Patches internal `start_db_select_task`/`cancel_task`/`reset_selection_status`/`check_db_selection_data`/`generate_selection_csvs`.

| Test (or group) | Bucket | Reason |
|---|---|---|
| start ×2 + invalid-selection error, cancel ×2 | KEEP-E2E-OTHER (celery) | `start_db_select_task`/`cancel_task` wrap Celery; candidate-once-celery-seam-exists |
| selected-CSV download, remaining-CSV download, report download | KEEP-SMOKE | **real end-to-end CSV/report generation** from persisted `SelectionRunRecord` (no stub) + UTF-8 BOM — strongest smokes |
| save-settings success, check-data (one) | KEEP-SMOKE | CSRF-exercising POST smokes |
| requires-auth (6), modal-progress fragments (4), download error branches (boundary-stub), report empty/unknown, page integration (3), reset (rewrite interaction→state, 2), selected-count (2), save-settings variants (3), settings-warning (3), history (2) (~32) | MOVE-COMPONENT | drop CSRF when moved; **rewrite the `reset`/`start`/`cancel` interaction-style assertions to state-based** |

**Recommendation:** ~4–5 smokes, ~32 component, 0 db_semantics, ~5 e2e-celery. Secondary gate: ~12 POST tests use real CSRF (component tier disables it) — keep one CSRF-exercising e2e smoke per POST route, drop CSRF on the moved variants.

---

### Group: gsheet routes / registration / misc

#### test_gsheets_routes.py
Routes: replacement progress modal, legacy redirects, start/cancel replacement load+run, manage-tabs list/delete/progress/cancel, selection-page context, "View Running" button. ~44 tests. **Group D — Celery-dominated.** Patches `start_gsheet_replace*_task`/`start_gsheet_manage_tabs_task`/`cancel_task`/`get_selection_run_status`/`check_and_update_task_health`/`get_manage_old_tabs_status`.

| Test (or group) | Bucket | Reason |
|---|---|---|
| start replacement load (3), start replacement run success, cancel (3), manage-tabs list/delete (4), progress modals (5), manage-tabs progress (5), selection-page-with-status-context (9) | KEEP-E2E-OTHER (celery) | dispatch + status-poll boundary; candidate-once-celery-seam-exists |
| replacement-run number validation (4), legacy redirects (3), no-task button render (1) | MOVE-COMPONENT | pre-dispatch validation / redirects / render over fake |
| `TestSelectionPageViewRunningButton` running/pending/completed/replacement (4, seed real `SelectionRunRecord`) | KEEP-SMOKE | keep 1–2 as the selection-card run-state PG smoke |

**Recommendation:** ~2 smokes, ~9 component, 0 db_semantics, ~33 e2e-celery. Mostly Celery-bound.

#### test_backoffice_gsheet_selection.py
Routes: data form (new/view/edit), gsheet save/delete, selection page/load/run, run view, modal-progress, cancel, history. ~56 tests. Patches `start_gsheet_load_task`/`start_gsheet_select_task`/`cancel_task`/`get_selection_run_status`/`check_and_update_task_health`.

| Test (or group) | Bucket | Reason |
|---|---|---|
| create/update gsheet happy paths (1–2), delete/state-transition (1) | KEEP-SMOKE | `/gsheet/save` + delete smoke |
| `test_update_gsheet_config_success_with_team_eu`, `_with_custom_team` | KEEP-DB-SEMANTICS | `selection_settings` JSON-list round-trip read back via `SqlAlchemyUnitOfWork` |
| config form renders (6), URL/address validation (8), warning branch, permission/auth (6), delete button-visibility/not-found, selection-tab renders (4), legacy URL→query redirect (~30) | MOVE-COMPONENT | render + validation over fake |
| ~18 selection load/run/cancel/modal-progress/current-selection/run-details (patch task dispatch + status-poll) | KEEP-E2E-OTHER (celery) | candidate-once-celery-seam-exists |

**Recommendation:** ~3 smokes, ~30 component, 2 db_semantics, ~18 e2e-celery. Largest single split.

#### test_registration_public.py  *(already trimmed in Phase 3 — leave as-is)*
Routes: register GET/POST, thank-you, short-url, registration-closed. 10 tests.

| Test (or group) | Bucket | Reason |
|---|---|---|
| `TestCspNonceNotLeakedToAuthorHtml`, 2× `TestRegistrationCsrfExpiry` | KEEP-E2E-OTHER | **CSP-nonce isolation + real CSRF** (flips `WTF_CSRF_ENABLED=True`) — MUST stay e2e |
| renders_published_form, thank-you, short-url redirect, closed page | KEEP-SMOKE | thin render/redirect smokes (richly covered in component already) |
| submission→POOL, test-mode→TEST_SUBMISSION | KEEP-SMOKE | real-DB respondent-status submission smokes |

**Recommendation:** Nothing to migrate. Behavioural coverage already in `tests/component/test_registration_routes.py`. Confirmed correctly trimmed. 3 e2e-other + 7 smokes.

#### test_registration_image_serve.py  *(already trimmed — leave as-is)*
Route: `GET /register/<slug>/assets/<image_name>`. 1 test → KEEP-SMOKE (real-DB BLOB round-trip + caching headers). Full matrix already in `tests/component/test_registration_image_serve.py` (7 tests). Plain `bytea` column, no special operators → KEEP-SMOKE, **not** db_semantics.

#### test_registration_auto_reply.py  *(already trimmed — leave as-is)*
Route: `POST /register/<slug>` auto-reply side effect. 1 test → KEEP-SMOKE (writes a SENT `RespondentEmailSendRecord` via the console adapter; real cross-table persistence). Variants already in `tests/component/test_registration_auto_reply.py` (4 tests).

#### test_resend_confirmation.py  *(net-new component work)*
Route: `GET/POST /auth/resend-confirmation`. 4 tests. No Celery; email via injectable `get_email_adapter()` (console adapter in tests); CSRF disabled.

| Test (or group) | Bucket | Reason |
|---|---|---|
| `test_resend_confirmation_form_submission_succeeds` | KEEP-SMOKE | anti-enumeration 302→login PG smoke |
| GET form render, invalid-email validation, missing-email validation | MOVE-COMPONENT | fully fake-compatible |

**Recommendation:** 1 smoke, 3 component (net-new `tests/component/test_resend_confirmation.py`), 0 db_semantics, 0 e2e-other.

---

### Group: infra / boundary endpoints (Group E — mostly stay)

#### test_health_check.py
Routes: `/health`, `/health/bdd`. 18 tests. **All KEEP-E2E-OTHER.** The endpoint's value is aggregating real DB/Celery boundary checks (deliberately mocked). The 10 Microsoft-OAuth-expiry + 3 BDD-health tests are pure config/date-math — technically convertible but gain nothing and would fragment one route's coverage. None warrant `db_semantics` (they mock the DB).

#### test_health_check_monitoring.py
Routes: `/health`, `/health/monitor_selection`. 10 tests.

| Test (or group) | Bucket | Reason |
|---|---|---|
| not-configured health 200, not-configured monitor 500 | KEEP-SMOKE | env-not-configured branch |
| 8 record-seeding tests (recent-completed, stale-too-old, no-records, latest-failed, latest-cancelled, cleanup-override, pending-window, running-too-long) | KEEP-DB-SEMANTICS | real `selection_run_records` latest-by-`created_at`/task-type/age/timestamp queries |

**Recommendation:** 2 smokes, 8 db_semantics, 0 component. The pure-logic coverage already exists in `tests/unit/test_monitoring_service.py` over a `FakeUnitOfWork` — these e2e tests are correctly the DB-semantics layer.

#### test_feature_flags_e2e.py
Routes: `/health`, `/auth/login`. 3 tests. **All KEEP-E2E-OTHER** — whole-app boot/registration probes for the `feature()` context processor; the flags machinery itself is unit-tested (`test_feature_flags.py`). Converting gains nothing.

#### test_wellknown.py
Routes: `/robots.txt`, `/.well-known/security.txt`, `/.well-known/change-password`. ~8–10 tests. **All KEEP-E2E-OTHER** — static-asset serving + auth-aware redirects, no service/DB dimension. The one logged-in redirect could run on the component app but moving a single test out of a cohesive file gains nothing.

---

## 5. Recommended order of work

The conversion is **per-file, test-guarded** (keep the suite green throughout). Suggested order, easiest/highest-value first:

1. **Clean, no-blocker files (pure component wins):** `test_profile_management.py`,
   `test_assembly_crud.py` (pilot-proven), `test_backoffice_general.py`,
   `test_2fa_flow.py`, `test_resend_confirmation.py`. Establishes the conversion
   pattern (drop CSRF token, `session_transaction` login, state-based asserts).
2. **Auth + admin (with the db_semantics carve-outs):** `test_auth_flow.py` (mind the
   Redis rate-limit + CSRF e2e-other), `test_admin_invite_management.py`,
   `test_admin_user_management.py` (mark the 4 `filter_paginated`/`search` tests
   `db_semantics`).
3. **Assembly + respondents + targets:** `test_backoffice_assembly.py`,
   `test_assembly_gsheet_crud.py`, `test_assembly_user_management.py`,
   `test_backoffice_respondents.py`, `test_backoffice_respondent_field_schema.py`,
   `test_respondents_pages.py`, `test_targets_pages.py`. Apply the `db_semantics`
   marks for the attribute-aggregation/JSON/ordering tests.
4. **Selection/gsheet non-Celery slices:** move the auth/authz/validation/render
   tail of `test_sortition_routes.py`, `test_db_selection_routes.py`,
   `test_db_selection_backoffice.py`, `test_backoffice_gsheet_selection.py`,
   `test_gsheets_routes.py` to component; leave the Celery tail e2e tagged
   `candidate-once-celery-seam-exists`. (db_selection_backoffice: keep one
   CSRF-exercising e2e smoke per POST route.)
5. **Mark-only (no move):** add `@pytest.mark.db_semantics` to the 8 monitoring
   tests in `test_health_check_monitoring.py` and the `db_semantics` keepers
   identified above.
6. **Leave as-is:** the three registration files (done), the four infra files
   (`test_health_check*.py`, `test_feature_flags_e2e.py`, `test_wellknown.py`).
7. **Legacy (resolved):** do not migrate `test_targets_legacy_pages.py` **or**
   `test_respondents_pages.py` — both blueprints are confirmed legacy and slated for
   deletion. Left untouched (they still cover live code until the blueprints are
   removed); delete each file with its blueprint.

## 6. Deferred / blocked-elsewhere

- **Celery boundary seam (phase-3 §6.4)** unblocks ~70 `candidate-once-celery-seam-exists`
  tests across the five selection/gsheet files. Until then they stay e2e.
- **OAuth fake-app fixture + provider mock** unblocks ~13 non-provider tests in
  `test_oauth_flow.py`. The provider-callback tests stay e2e regardless.
- **Redis-backed login rate-limiting** (5 tests in `test_auth_flow.py`) needs real
  Redis and stays e2e regardless of any seam.
