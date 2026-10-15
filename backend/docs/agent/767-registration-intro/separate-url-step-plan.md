# A step of its own for the page name and URLs

Branch: `767-separate-url-step`, off `767-rich-text-autoreply`.

**Status: implemented.** Chewie answered the questions; the decisions
are below as P1–P8. Steps are marked ✅ as they are done.

## Goal

The registration editor's steps become:

1. **Name and URLs**: the page name, the registration
   URL and the short URL
2. Intro
3. Form
4. Auto-reply email
5. Preview and publish

Today the name and URLs sit at the top of the intro step, and only appear
in edit mode. Moving them out gives the intro step one job, and puts the
settings that apply to the whole page first, before any content.

## How it works today (what this touches)

| Layer    | Where                                                       | Today                                                                                                                                                                                                                                                                                                                                                                            |
| -------- | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Stepper  | `templates/backoffice/assembly_registration.html`           | Four `stepper()` items, keys `intro`, `form`, `email` and `preview`, each linking to `?section=<key>`. The stepper numbers them with `loop.index`, so adding an item renumbers the rest without further changes. Comments say "four steps".                                                                                                                                      |
| Template | `registration/_step_intro.html`                             | In edit mode the heading becomes a `page_name` input, followed by the "locked while published" alert and two `prefixed_url_input`s (`url_slug` and `short_url_slug`, both disabled when `slugs_frozen`). In read mode it shows the name as an `<h2>` and doesn't show the URLs. The footer has Next and no Back ("Step 1 has nowhere to go back to"). The ABOUTME says "Step 1". |
| Template | `_step_form.html`, `_step_email.html`, `_step_preview.html` | ABOUTMEs say Steps 2, 3 and 4. The form step's Back goes to `section="intro"`, and a comment there says the page is named "on the intro step".                                                                                                                                                                                                                                   |
| Template | `_step_preview.html`                                        | A "Share your form" aside, showing the URLs read-only, the short URL and the QR code with a download link.                                                                                                                                                                                                                                                                       |
| Route    | `backoffice_registration.py` `view_registration_page`       | `active_section = request.args.get("section", "intro")`, falling back to `"intro"` for anything not in `_SECTIONS`.                                                                                                                                                                                                                                                              |
| Route    | `save_assembly_registration`                                | One save route for every step. `_save_origin()` reads the origin from the posted fields: `"intro"` if `intro_content` is present, `"form"` otherwise. `_post_action_section` sends `save_and_next` to `_SECTIONS[index + 1]`. `_apply_page_settings` saves `page_name`, `url_slug` and `short_url_slug` whenever they are posted, and the redirect uses the new slug.            |
| Route    | `create_assembly_registration_page`                         | Redirects to `editor_url(...)` with no section, so to the intro. Flashes "Registration page created. URLs have been generated automatically and can be edited below." In practice they can only be edited after clicking Edit on the intro step.                                                                                                                                 |
| Hub      | `registration_hub.py` `editor_url`                          | The pages list's rows link to the editor with no section.                                                                                                                                                                                                                                                                                                                        |

Tests that depend on the step order or on where the name is edited:

- `tests/component/test_backoffice_registration_view.py`:
  - `TestEditorNameAndSlugEditing` posts `intro_content` together with `page_name` or `url_slug`, and checks the intro step offers the inputs.
  - Stepper order (line ~321), default section (~303 and ~312), and redirects that go to `section=intro` (~357 and ~398).
- `tests/component/test_backoffice_registration_page_script.py:134`: lists every section.
- `tests/e2e/test_registration_stepper_journey.py`: "Creation lands on the editor's first step, the intro", then walks intro → form → email → preview.
- `tests/bdd/test_backoffice.py:785`: "Opening a page from the list lands on its first step, the intro".

## Decisions

### P1: The section key is `page` (Chewie)

The step is `?section=page`. It's short, and it matches `page_name`. Old links
that say `?section=intro` keep working and still open the intro, so no
redirect is needed.

### P2: The step is labelled "Name and URLs" (Chewie)

The label is used in the stepper and as the step's heading. It says exactly
what is on the step.

### P3: Opening a page lands on step 1 (Chewie)

`page` becomes the default section and the fallback for an unknown section.
The pages list, a bare editor URL and creating a page all land on step 1. The
"first step" rule in the tests stays true, with step 1 now the new step. The
create flash ("URLs have been generated automatically and can be edited
below") becomes accurate, so it isn't changed and no translation is lost.

### P4: Step 1's read view shows the values read-only (Chewie)

- **Name:** shown as the step's text.
- **URLs:** both shown with `readonly_url_display` and its copy buttons, as
  on the preview step. The short URL is shown only when one is set.
- **Locked alert:** shown when `slugs_frozen`, so it's clear why Edit won't
  change them.
- **Preview step:** keeps its "Share your form" panel, with the QR code,
  unchanged.

### P5: Step 1 uses the same Edit / Save / Cancel pattern (Chewie)

- **Header:** Edit while viewing, and Cancel and Save while editing. Save
  becomes "Save and Republish" when the page is published.
- **While editing:** the dirty-guard is on, and the stepper and Next are
  disabled.
- **Closed pages:** there is no Edit, as on the other steps.

### P6: A hidden `step` field says which step posted (Chewie)

- **Each step's form posts a hidden `step` field.** `_save_origin()` reads it
  and accepts only a value in `_SECTIONS`.
- **Without it, the origin is `"form"`,** as lifecycle posts are treated
  today.
- **The intro step stops posting the page fields:** `page_name`, `url_slug`
  and `short_url_slug`. `_apply_page_settings` already treats missing fields
  as "leave alone", so it needs no change.

### P7: Save only, no "Save and next" (Chewie)

Step 1 has Save only, like the other steps. The route keeps supporting
`save_and_next`, which now goes page → intro → form → email.

### P8: Only the three fields move (Chewie)

Nothing else that applies to the whole page moves to step 1, for now at
least. Content style stays on the intro, and the auto-reply template is still
assigned on the email step.

### Decisions that didn't need a question

- **The intro step's heading becomes the page name as plain text**, the same
  as on the form step (`<h2>{{ registration_page.name }}</h2>`). The dialog
  title already shows the name too.
- **The intro step gains a Back button** to step 1, using the same markup as
  the form step's footer. Step 1 takes over the "nowhere to go back to"
  footer.
- **A failed slug change** (taken or invalid) lands back on step 1 in edit
  mode, with the old slug in the URL. The transaction rolls back, so the old
  slug is still the right one.
- **The Assets panel stays on the intro.** Step 1 has no use for it, so it is
  a single column.
- **No JavaScript change is expected.** `registrationPageController`'s
  dirty-guard hangs off the form's `@input` and `@change` events, which step
  1 has too. Step 1 does need adding to
  `test_backoffice_registration_page_script.py`'s list of views, to prove the
  script loads there.

## Steps

Each step is committed on its own, after `just check` and the relevant tests
pass.

### Step 1: Route ✅

- `_SECTIONS = ("page", "intro", "form", "email", "preview")`.
- `_save_origin()` reads the posted `step` field (P6). Update its docstring,
  `_post_action_section`'s docstring and `save_assembly_registration`'s action
  list to match.
- Each existing step's form gains its hidden `step` field in the same
  commit. The intro and the form are the only ones that post to this route.
  Without the field, an intro save would be treated as coming from the form.
- Component tests in `test_backoffice_registration_view.py`:
  - **Saving from step 1:** a save lands back on step 1, and `save_and_next`
    lands on the intro.
  - **Saving from the intro:** a save posting `step=intro` lands on the
    intro.
  - **A missing or unknown `step`:** treated as the form.
  - **A failed slug save** lands on `section=page&edit=1`.

As built:

- **The default section moved to step 2.** Making `page` the default before
  its template exists would have opened every page on an empty step, so the
  default and fallback change in step 2, alongside the template.
- **Lifecycle posts weren't retested.** The existing tests already cover
  them landing on the preview step, and the preview and modal forms carry no
  `step`.
- **Two tests in the e2e journey changed.** Its intro and form posts now send
  `step`.
- **The page-name and slug tests** in `TestEditorNameAndSlugEditing` now post
  `step=page` with only the page fields.
- **New tests:** each step's form posts its name; a save without a known step
  goes to the form; a taken slug keeps the old slug and returns to
  `section=page&edit=1`.

### Step 2: Templates ✅

- **New `registration/_step_page.html`:**
  - The name input, the locked alert and the two `prefixed_url_input`s move
    here out of `_step_intro.html`.
  - It has the read view (P4), the Edit/Cancel/Save header (P5), the hidden
    `step=page` field and a footer with Next only.
- **`_step_intro.html`:**
  - The heading becomes plain text, the URL block goes, and a Back button is
    added.
  - The ABOUTME says Step 2.
- **`_step_form.html`, `_step_email.html` and `_step_preview.html`:**
  renumber their ABOUTMEs to 3, 4 and 5, and fix the form step's comment
  about where the page is named.
- **`view_registration_page`:** `page` becomes the default section and the
  fallback for an unknown one. Update the tests that assumed the intro was
  the default (around lines 303, 312 and 145).
- **`assembly_registration.html`:**
  - Add the `page` stepper item, labelled "Name and URLs", first.
  - Add the `include`.
  - Update the comments that say "four steps" and "intro → form → …".
- **Component tests:**
  - Move `TestEditorNameAndSlugEditing` to step 1. The name and slug inputs
    are on step 1 in edit mode, and absent from the intro and the form, both
    in edit mode.
  - Step 1's read view shows the name and both URLs. It doesn't show the
    short URL when none is set.
  - When `slugs_frozen`, step 1 shows the locked alert, both read-only and
    in edit mode, and the slug inputs are disabled.
  - Update the stepper order test to page < intro < form < email.
  - Add `section=page` and `section=page&edit=1` to the page-script view
    list.

As built:

- **Step 1 is a single column, as decided.** The name uses the `input`
  macro: a text input with a visible label while editing, and plain text
  otherwise.
- **The locked alert shows whether or not you're editing**, whenever
  `slugs_frozen`.
- **`TestViewEditModeFlag` now names `?section=intro`.** It used the default
  section, which is no longer the intro.
- **The e2e journey was brought forward from step 3.** Without it this
  commit would have left it failing. It now renames the page and changes
  both slugs on step 1 with `save_and_next`, lands on the intro at the new
  slug, and carries on with that slug.
- **New tests cover step 1:**
  - its edit and read views, including leaving out an unset short URL;
  - its footer (Next, no Back);
  - the locked alert and the disabled slug input on a published page;
  - no Edit on a closed page;
  - the intro's Back link.

### Step 3: Journeys ✅

- **`tests/e2e/test_registration_stepper_journey.py`:** done in step 2.
- **BDD, after `just build-all`:**
  - Update "Opening a page from the list lands on its first step".
  - Add a scenario to `backoffice-registration-editor.feature`: rename the
    page and change its URL on step 1, save, and see the new name in the
    dialog title and the new slug in the address bar.
  - Check that existing steps opening `?section=intro&edit=1` still find what
    they look for, now that the name input has gone from there.

As built:

- **The two list scenarios now end on step 1.** They use a new "read-only name
  and URLs view" step. The intro's read-only step was used nowhere else, so
  it was removed.
- **"The stepper navigation should be disabled"** now counts five disabled
  steps.
- **The new scenario clicks Edit as a button.** The `button` macro renders
  links with `role="button"`.
- **The intro-editing scenarios needed no change.** They open
  `?section=intro&edit=1` and never touched the name input.
- **Results:** full BDD run 218 passed and 5 skipped, then the two fixed
  scenarios passed on a rerun.
- **Checked by eye:** screenshots of step 1, read-only and editing, at
  1400px.

### Step 4: Catalogues and docs ✅

- **Catalogues:** run `just translate-regen` and `just translate-check`. The
  new string is the "Name and URLs" label. The rest reuse existing msgids.
  The Hungarian is left for a translator.
- **`docs/registration-intro-editor.md`:** check it doesn't say the URLs are
  on the intro step. I found nothing, but I'll look again once the code is
  done.

As built:

- **Catalogues:** the regen added one msgid, "Name and URLs". No msgid was
  removed and no translation changed. The rest of the diff is source
  references moving.
- **Docs:** none needed changing. `docs/language.md`'s "registration step 1"
  is about the hub's set-up steps, not the editor's.
