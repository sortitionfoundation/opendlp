# Registration Form — Public Rendering and Submission Plan

**Branch:** `610-registration-page-html`
**Date:** 2026-05-22
**Status:** Draft — covers rendering the public form and accepting submissions
**Depends on:** `plan-data-service.md` (domain layer complete), recent commits (Jinja sandbox rendering)

This plan covers implementing the public-facing registration form routes and submission handling — the "form-submission story" deferred in `plan-data-service.md` §8.

---

## 1. Scope

**In scope:**

- Public routes: `/register/<url_slug>` (GET/POST), `/r/<short_url_slug>` (GET, 302 redirect)
- `/registration-closed` static page
- Form rendering using Jinja sandbox (already implemented in domain)
- Form submission handling (POST)
- Validation against assembly's `RespondentFieldDefinition` schema
- Creating `Respondent` records with correct status (`POOL` or `TEST_SUBMISSION`)
- Thank-you page rendering
- Test-page banner for `TEST` status
- `RespondentStatus.TEST_SUBMISSION` enum value

**Out of scope (future stories):**

- Bot protection / CAPTCHA
- Rate limiting
- Thank-you page placeholders (`{{ respondent_name }}`, etc.)
- Email confirmation/auto-reply
- Multiple registration forms per assembly
- Form translations

---

## 2. Current State Analysis

### 2.1 What's already implemented

**Domain layer (`domain/registration_page.py`):**
- `RegistrationPage` aggregate with `TEST / PUBLISHED / CLOSED` status
- `RegistrationPageHtml` with Jinja sandbox rendering
- `RenderContext` dataclass with `csrf_form_element`, `form_action`, `values`, `errors`, `form_level_errors`
- Template helpers: `value()`, `checked()`, `selected()`, `field_errors()`, `has_error()`, `first_error()`, `form_errors()`
- `generate_starter_form_html()` pure function
- `readiness_problems()` using `jinja2.meta` for parse-based validation

**Service layer (`service_layer/registration_page_service.py`):**
- `find_registration_page_by_url_slug(uow, url_slug)` — lookup for `/register/<slug>`
- `find_registration_page_by_short_url_slug(uow, short_url_slug)` — lookup for `/r/<slug>`
- `resolve_visibility(page)` — returns `LIVE | TEST | CLOSED | NOT_FOUND`
- `get_page_and_source_for_render(uow, assembly_id)` — loads HTML source
- `render_thank_you_html(uow, assembly_id)` — returns thank-you HTML verbatim

**Backoffice routes:**
- Full CRUD for registration page configuration
- Status transitions (publish/unpublish/close/reopen)
- "Show Form Skeleton" modal with copy functionality

### 2.2 What's missing

1. **`RespondentStatus.TEST_SUBMISSION`** — new enum value in `domain/value_objects.py`
2. **Public blueprint routes** — new file `blueprints/register.py` (or extend `main.py`)
3. **Form submission handler** — POST endpoint that validates and creates Respondent
4. **Field validation service** — maps POST data to `RespondentFieldDefinition` schema
5. **Test-page banner** — UI indicator when viewing `TEST` status forms
6. **Templates** — `register_form.html`, `registration_closed.html`, `thank_you.html`

---

## 3. Implementation Plan

### Phase 1: Domain Changes

#### 3.1 Add `TEST_SUBMISSION` to `RespondentStatus`

**File:** `src/opendlp/domain/value_objects.py`

```python
class RespondentStatus(Enum):
    """Status of a respondent in the selection process"""

    TEST_SUBMISSION = "TEST_SUBMISSION"  # New: submission from TEST page
    POOL = "POOL"
    SELECTED = "SELECTED"
    CONFIRMED = "CONFIRMED"
    WITHDRAWN = "WITHDRAWN"
    DELETED = "DELETED"
```

**Update `ALLOWED_SELECTION_STATUS_TRANSITIONS`:**
- `TEST_SUBMISSION` cannot transition to selection states (quarantined from pool)
- Can transition to `DELETED` (GDPR delete) and potentially `POOL` (promote to real submission)

```python
ALLOWED_SELECTION_STATUS_TRANSITIONS: dict["RespondentStatus", list["RespondentStatus"]] = {
    RespondentStatus.TEST_SUBMISSION: [RespondentStatus.POOL],  # Can promote to real
    RespondentStatus.POOL: [RespondentStatus.SELECTED, RespondentStatus.CONFIRMED, RespondentStatus.WITHDRAWN],
    RespondentStatus.SELECTED: [RespondentStatus.POOL, RespondentStatus.CONFIRMED, RespondentStatus.WITHDRAWN],
    RespondentStatus.CONFIRMED: [RespondentStatus.POOL, RespondentStatus.SELECTED, RespondentStatus.WITHDRAWN],
    RespondentStatus.WITHDRAWN: [RespondentStatus.POOL, RespondentStatus.SELECTED, RespondentStatus.CONFIRMED],
    RespondentStatus.DELETED: [],
}
```

**Migration:** Add migration to handle any existing data (none expected on this branch).

---

### Phase 2: New Public Blueprint

#### 3.2 Create `blueprints/register.py`

New blueprint for public registration routes. Separate from `main.py` for clarity.

```python
# ABOUTME: Public registration form routes
# ABOUTME: Handles form display and submission at /register/<slug>

from flask import Blueprint

register_bp = Blueprint("register", __name__)
```

**Routes:**

| Route | Method | Handler | Description |
|-------|--------|---------|-------------|
| `/register/<url_slug>` | GET | `view_registration_form` | Render form (or redirect if closed) |
| `/register/<url_slug>` | POST | `submit_registration_form` | Process submission |
| `/r/<short_url_slug>` | GET | `short_url_redirect` | 302 redirect to canonical |
| `/registration-closed` | GET | `registration_closed` | Static "closed" page |

**Wire up in `create_app`:** Add `register_bp` to app blueprints in `src/opendlp/entrypoints/app.py`.

---

### Phase 3: Form Rendering (GET)

#### 3.3 `view_registration_form` handler

```python
@register_bp.route("/register/<url_slug>", methods=["GET"])
def view_registration_form(url_slug: str) -> ResponseReturnValue:
    """Display the registration form for the given assembly."""
    uow = bootstrap.bootstrap()
    page = find_registration_page_by_url_slug(uow, url_slug)

    visibility = resolve_visibility(page)

    if visibility == RegistrationPageVisibilityState.NOT_FOUND:
        abort(404)

    if visibility == RegistrationPageVisibilityState.CLOSED:
        return redirect(url_for("register.registration_closed"), code=302)

    # LIVE or TEST — render the form
    uow = bootstrap.bootstrap()
    page, source = get_page_and_source_for_render(uow, page.assembly_id)

    ctx = RenderContext(
        csrf_form_element=Markup(render_csrf_hidden_input()),
        form_action=url_for("register.submit_registration_form", url_slug=url_slug),
        values={},
        errors={},
        form_level_errors=[],
    )

    rendered_html = source.render(ctx)
    is_test_mode = (visibility == RegistrationPageVisibilityState.TEST)

    return render_template(
        "public/register_form.html",
        form_html=Markup(rendered_html),
        is_test_mode=is_test_mode,
        assembly_title=get_assembly_title(uow, page.assembly_id),
    )
```

#### 3.4 Short URL redirect

```python
@register_bp.route("/r/<short_url_slug>", methods=["GET"])
def short_url_redirect(short_url_slug: str) -> ResponseReturnValue:
    """Redirect short URL to canonical /register/<url_slug>."""
    uow = bootstrap.bootstrap()
    page = find_registration_page_by_short_url_slug(uow, short_url_slug)

    if page is None or not page.url_slug:
        abort(404)

    # 302 (temporary) — short slugs may be reused later
    return redirect(
        url_for("register.view_registration_form", url_slug=page.url_slug),
        code=302
    )
```

---

### Phase 4: Form Submission (POST)

#### 3.5 `submit_registration_form` handler

```python
@register_bp.route("/register/<url_slug>", methods=["POST"])
def submit_registration_form(url_slug: str) -> ResponseReturnValue:
    """Process registration form submission."""
    uow = bootstrap.bootstrap()
    page = find_registration_page_by_url_slug(uow, url_slug)

    visibility = resolve_visibility(page)

    if visibility == RegistrationPageVisibilityState.NOT_FOUND:
        abort(404)

    if visibility == RegistrationPageVisibilityState.CLOSED:
        return redirect(url_for("register.registration_closed"), code=302)

    # Validate form data against assembly's field schema
    uow = bootstrap.bootstrap()
    field_definitions = get_field_definitions_for_assembly(uow, page.assembly_id)

    form_data = request.form.to_dict()
    validation_result = validate_registration_submission(field_definitions, form_data)

    if not validation_result.is_valid:
        # Re-render form with errors
        page, source = get_page_and_source_for_render(uow, page.assembly_id)

        ctx = RenderContext(
            csrf_form_element=Markup(render_csrf_hidden_input()),
            form_action=url_for("register.submit_registration_form", url_slug=url_slug),
            values=form_data,
            errors=validation_result.field_errors,
            form_level_errors=validation_result.form_errors,
        )

        rendered_html = source.render(ctx)
        is_test_mode = (visibility == RegistrationPageVisibilityState.TEST)

        return render_template(
            "public/register_form.html",
            form_html=Markup(rendered_html),
            is_test_mode=is_test_mode,
            assembly_title=get_assembly_title(uow, page.assembly_id),
        ), 422  # Unprocessable Entity

    # Determine respondent status based on page status
    respondent_status = (
        RespondentStatus.TEST_SUBMISSION
        if visibility == RegistrationPageVisibilityState.TEST
        else RespondentStatus.POOL
    )

    # Create respondent
    uow = bootstrap.bootstrap()
    respondent = create_respondent_from_submission(
        uow,
        assembly_id=page.assembly_id,
        validated_data=validation_result.cleaned_data,
        source_type=RespondentSourceType.REGISTRATION_FORM,
        selection_status=respondent_status,
    )

    # Render thank-you page
    uow = bootstrap.bootstrap()
    thank_you_html = render_thank_you_html(uow, page.assembly_id)

    return render_template(
        "public/thank_you.html",
        thank_you_html=Markup(thank_you_html),
        is_test_mode=(respondent_status == RespondentStatus.TEST_SUBMISSION),
    )
```

---

### Phase 5: Validation Service

#### 3.6 New service function: `validate_registration_submission`

**File:** `src/opendlp/service_layer/registration_submission_service.py` (new file)

```python
@dataclass
class ValidationResult:
    """Result of validating a registration form submission."""
    is_valid: bool
    cleaned_data: dict[str, Any]  # field_key → validated value
    field_errors: dict[str, list[str]]  # field_key → error messages
    form_errors: list[str]  # form-level errors

def validate_registration_submission(
    field_definitions: list[RespondentFieldDefinition],
    form_data: dict[str, str],
) -> ValidationResult:
    """Validate form submission against assembly's field schema."""
```

**Validation rules per field type:**

| FieldType | Validation |
|-----------|------------|
| `TEXT` | Required check, max length |
| `EMAIL` | Required check, email format |
| `PHONE` | Required check, phone format (lenient) |
| `BOOLEAN` | Coerce to bool |
| `SINGLE_SELECT` | Value in `choice_options` |
| `MULTI_SELECT` | All values in `choice_options` |
| `DATE` | Valid date format |
| `INTEGER` | Valid integer |

**Required field handling:**
- `RespondentFieldDefinition.is_required` determines if field must be non-empty
- Fixed fields (`is_fixed=True`) like `email`, `consent` have hardcoded requirements

---

### Phase 6: Respondent Creation

#### 3.7 New/extended service function

Either extend existing `create_respondent` or add:

```python
def create_respondent_from_submission(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    validated_data: dict[str, Any],
    source_type: RespondentSourceType,
    selection_status: RespondentStatus,
) -> Respondent:
    """Create a respondent from a validated form submission.

    Unlike create_respondent, this does NOT require a user_id (public submission).
    The external_id is auto-generated (timestamp + random suffix or UUID).
    """
```

**Key differences from existing `create_respondent`:**
- No `user_id` required (public submission, no logged-in user)
- Auto-generates `external_id` (e.g., `reg-<timestamp>-<random>`)
- Maps validated data to `attributes` dict
- Sets `source_type=REGISTRATION_FORM`
- Sets `selection_status` based on page status

---

### Phase 7: Templates

#### 3.8 Template files

**`templates/public/register_form.html`:**
```jinja
{% extends "public/base.html" %}

{% block content %}
{% if is_test_mode %}
<div class="test-mode-banner" role="alert">
    {{ _("This is a test registration form. Submissions will be recorded as test data.") }}
</div>
{% endif %}

{{ form_html }}
{% endblock %}
```

**`templates/public/thank_you.html`:**
```jinja
{% extends "public/base.html" %}

{% block content %}
{% if is_test_mode %}
<div class="test-mode-banner" role="alert">
    {{ _("This was a test submission. Your data has been recorded as test data.") }}
</div>
{% endif %}

{{ thank_you_html }}
{% endblock %}
```

**`templates/public/registration_closed.html`:**
```jinja
{% extends "public/base.html" %}

{% block content %}
<h1>{{ _("Registration Closed") }}</h1>
<p>{{ _("Registration for this assembly has closed.") }}</p>
{% endblock %}
```

**`templates/public/base.html`:**
- Minimal base template for public pages
- No login required, no backoffice navigation
- CSP nonce support
- Basic styling (GOV.UK or minimal)

---

## 4. Service-Docs Updates

Update `/backoffice/dev/service-docs?tab=registration` with:

### 4.1 New public routes section

Document the public-facing routes:
- `GET /register/<url_slug>` — render form
- `POST /register/<url_slug>` — submit form
- `GET /r/<short_url_slug>` — redirect to canonical
- `GET /registration-closed` — static closed page

### 4.2 New service functions

- `validate_registration_submission(field_definitions, form_data)` → `ValidationResult`
- `create_respondent_from_submission(uow, assembly_id, validated_data, source_type, selection_status)` → `Respondent`

### 4.3 RenderContext helpers documentation

Document the Jinja template helpers available in form HTML:
- `{{ value(field_key) }}` — get submitted value
- `{{ checked(field_key, option_value) }}` — "checked" if matches
- `{{ selected(field_key, option_value) }}` — "selected" if matches
- `{{ field_errors(field_key) }}` — HTML list of field errors
- `{{ has_error(field_key) }}` — boolean, has errors
- `{{ first_error(field_key) }}` — first error message
- `{{ form_errors() }}` — HTML list of form-level errors

---

## 5. Testing Strategy

### 5.1 Unit tests

- `test_validate_registration_submission.py` — validation logic
- `test_create_respondent_from_submission.py` — respondent creation

### 5.2 Contract tests

- Repository tests for `TEST_SUBMISSION` status handling
- Ensure `TEST_SUBMISSION` respondents don't appear in selection queries

### 5.3 Integration tests

- Full POST flow: submit → validate → create respondent → thank-you
- Re-render with errors on validation failure
- `TEST` vs `PUBLISHED` status routing to correct `RespondentStatus`

### 5.4 BDD tests

- "As a visitor, I can submit the registration form and see a thank-you page"
- "As a visitor, I see error messages when I submit invalid data"
- "When the registration is closed, I am redirected to the closed page"

---

## 6. Implementation Order

1. **Domain:** Add `TEST_SUBMISSION` to `RespondentStatus` + migration
2. **Service:** Add `validate_registration_submission` function
3. **Service:** Add/extend `create_respondent_from_submission` function
4. **Blueprint:** Create `register.py` with GET routes (form display)
5. **Templates:** Create public templates
6. **Blueprint:** Add POST route (form submission)
7. **Tests:** Unit, contract, integration tests
8. **Service-docs:** Update documentation

---

## 7. Open Questions

### Q1 — Public base template

Do we use GOV.UK styling for public forms, or minimal custom styling?

**Recommendation:** Minimal base template with CSS variables. The form HTML itself is author-controlled, so the wrapper should be neutral.

### Q2 — Duplicate submission handling

What if someone submits the same form twice (refresh, back button)?

**Options:**
- (a) Allow duplicates — let backoffice dedup manually
- (b) Redirect-after-POST pattern — redirect to thank-you with flash
- (c) Session-based token — prevent re-submit within session

**Recommendation:** Option (b) — Redirect-after-POST is standard practice. Store respondent ID in session, redirect to `/register/<slug>/thank-you?id=<respondent_id>`.

### Q3 — Test submission visibility in backoffice

Should `TEST_SUBMISSION` respondents appear in the respondents list by default?

**Recommendation:** Show them but with a visual indicator (badge). Add filter to hide/show test submissions.

### Q4 — robots.txt

Should `/register/` be indexed by search engines?

**Note:** Recent commit `1d87c4e` already added robots noindex. Verify this covers `/register/` routes.

---

## 8. Dependencies

- `plan-data-service.md` — domain and service layer (complete)
- Recent commits — Jinja sandbox rendering (complete)
- `deltas-to-fix.md` — all decisions recorded (complete)

---

## 9. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| CSRF bypass on public form | Flask-WTF CSRF protection via `{{ csrf_form_element }}` |
| XSS in form HTML | Jinja sandbox with autoescape; author-supplied HTML is trusted |
| Spam submissions | Out of scope (bot protection in future story) |
| Field schema mismatch | Validate against assembly's `RespondentFieldDefinition` at submit time |

---

## 10. Implementation Progress

### Completed (2026-05-22)

- [x] Added `TEST_SUBMISSION` to `RespondentStatus` enum
- [x] Created `registration_submission_service.py` with:
  - `submit_registration()` for URL-based submissions
  - `submit_registration_by_assembly_id()` for testing
  - Field validation against assembly schema
- [x] Added service-docs Try It form for `submit_registration`
- [x] Wired up dev.py handler

### Pending

- [ ] Public routes (`/register/<url_slug>` GET/POST)
- [ ] Thank-you page template
- [ ] Test-mode banner
- [ ] BDD tests
