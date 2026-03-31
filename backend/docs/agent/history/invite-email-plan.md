# Plan: Save and Display Invite Email Address

## Summary

The email address passed when creating an invite is currently only used to send the email and then discarded. We need to persist it on the `UserInvite` domain model and display it in the admin views.

## Files to Modify

| Layer | File | Change |
|-------|------|--------|
| Domain | `src/opendlp/domain/user_invites.py` | Add `email` attribute |
| ORM | `src/opendlp/adapters/orm.py` | Add `email` column to `user_invites` table |
| Migration | `migrations/versions/xxx_add_email_to_user_invites.py` | New Alembic migration |
| Service | `src/opendlp/service_layer/invite_service.py` | Accept and persist `email` in `generate_invite()` / `generate_batch_invites()` |
| Blueprint | `src/opendlp/entrypoints/blueprints/admin.py` | Pass email to service when creating invite |
| Template | `templates/admin/invites.html` | Show email column in invite list table |
| Template | `templates/admin/invite_view.html` | Show email in invite detail view |
| CLI | `src/opendlp/entrypoints/cli/invites.py` | Show email in `invites list` output |
| Tests | Various | Red tests first, then green |

## TDD Steps (Red/Green cycles)

### Cycle 1: Domain Model

1. **RED** - Add test in `tests/unit/domain/test_user_invites.py`: `UserInvite` accepts optional `email` param, defaults to `""`, and stores it
2. **GREEN** - Add `email: str = ""` to `UserInvite.__init__()` and store as attribute. Update `create_detached_copy()` to include it.

### Cycle 2: Service Layer - generate_invite

3. **RED** - Add test in `tests/unit/test_invite_service.py`: `generate_invite()` accepts `email` kwarg and the returned invite has that email
4. **GREEN** - Update `generate_invite()` signature and pass email to `UserInvite()`

### Cycle 3: Service Layer - generate_batch_invites

5. **RED** - Add test: `generate_batch_invites()` accepts `email` kwarg and all returned invites have it
6. **GREEN** - Update `generate_batch_invites()` similarly

### Cycle 4: ORM + Migration

7. Add `email` column (nullable `String`, default `""`) to the `user_invites` table in `orm.py`
8. Generate Alembic migration

### Cycle 5: E2E - Create invite saves email

9. **RED** - Add test in `tests/e2e/test_admin_invite_management.py`: creating an invite with an email saves it, and viewing the invite shows the email
10. **GREEN** - Update `create_invite()` in `admin.py` to pass `email` to `generate_invite()`

### Cycle 6: E2E - List invites shows email

11. **RED** - Add test: the invites list page shows the email address column
12. **GREEN** - Update `templates/admin/invites.html` to add an Email column

### Cycle 7: E2E - View invite shows email

13. **RED** - Add test: the invite detail page shows the email address
14. **GREEN** - Update `templates/admin/invite_view.html` to show email

### Cycle 8: CLI (minor)

15. Update CLI `invites list` to display email - light-touch, test via existing patterns

## Design Decisions

- **`email` defaults to `""`** (not `None`) - consistent with the project's preference for empty string over `str | None`
- **Column is nullable** in the DB for backward compat with existing rows (migration sets default `""`)
- **No GDPR concern** - the email is the email the invite was *sent to*, not necessarily the registrant's email. It's operational metadata for admins. But we should consider this.
- **`create_detached_copy()`** must copy the email field too, or it'll be lost when returned from the service layer

## GDPR Note

Storing email addresses on invites creates a new place where personal data lives. The existing GDPR strategy is to blank data but keep the row. If an invite recipient requests deletion, we'd need to blank this field. This is a small addition to the existing pattern.
