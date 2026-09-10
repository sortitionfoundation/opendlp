# Ticket: two places where the page language is decided wrongly

Found while fixing `<html lang="en">`, which every base template hardcoded even
when the body was Hungarian. That attribute is fixed — it now follows the
negotiated locale. Fixing it exposed two cases where the *negotiated* locale is
itself the wrong answer, and one where negotiation cannot happen at all.

## Background: how the language is chosen

`get_locale()` in `src/opendlp/entrypoints/extensions.py` picks a base language
from, in order: the `?lang=` parameter, the session, `current_user`'s stored
preference, then `Accept-Language`. That base is then qualified with a region
from `Accept-Language`, so `en` + `en-GB` becomes `en_GB` — gettext falls back
`en_GB` → `en`, and dates and numbers get the regional format.

Two things about that chain are worth knowing before reading the rest:

- **Step 3 is dead code today.** It is guarded by
  `hasattr(current_user, "preferred_language")`, and `User` has no such
  attribute — not on the domain object, not in the ORM mapping. It is written
  for a feature `docs/translations.md` lists as future. Nothing is broken by
  it, but do not read the chain as if a stored preference exists.
- **The chain needs a request.** Everything below follows from that.

## 1. A registration page ignores the language it was built in

`RegistrationPage.language` exists (`domain/registration_page.py:187`), is
settable (`set_language`, wired through `registration_page_service.py:594`), and
is rendered as a tag in the backoffice page list. It is never read when the page
is served.

`blueprints/registration.py:148` renders `register/form.html` with
`rendered_form` and `is_test` and nothing else, so the public form comes out in
whatever locale the *visitor's* browser negotiated. An organiser who builds a
Hungarian registration page and sends the link to Hungarian speakers gets an
English form for anyone whose browser says `Accept-Language: en`.

This is the case where negotiation is simply the wrong policy. A registration
page has one authoritative language — the organiser chose it, the surrounding
letter or poster is in it, and the questions on the page are written in it. The
visitor's browser setting is not evidence about which language *this page* is
in.

What it needs:

- The four `register/*.html` templates that extend `base_public.html` should
  take their `lang` from `page.language`, not from `html_lang()`. A
  `{% block html_lang %}` on `base_public.html` is the small version.
- More substantially, the whole render should be forced to that locale, so the
  furniture around the organiser's own text — buttons, validation messages,
  the closed-page notice — matches. `flask_babel.force_locale` is the tool.
- `page.language` is a free-text field (`language.strip()`, no validation).
  Forcing a locale from it means it has to become a real language code, which
  is a data question about whatever is already stored, not just a form change.

Worth noting the tag currently renders `page.language` raw in
`backoffice/components/registration_page_list.html:55` and
`assembly_details.html:116`, so whatever is in there is already on screen.

## 2. Emails go out in the sender's language

Emails render through `FlaskTemplateRenderer` (`adapters/template_renderer.py:54`),
which opens `self.app.app_context()` — an app context, with no request. The
sending itself, though, happens during a request: no Celery task sends mail
(`entrypoints/celery/tasks.py` has none) and the invite CLI only prints codes.

So the locale in force when an invite renders is the one negotiated for the
**admin who clicked the button**. An admin working in Hungarian invites an
English speaker and the invite arrives in Hungarian.

There is a second, sharper edge here. `flask_babel.get_locale()` resolves
against `g`, which exists in a bare app context, so it calls our selector — and
our selector reads `request.args`. Outside a request that raises:

```
RuntimeError: Working outside of request context.
  extensions.py:134  requested_language = request.args.get("lang")
```

Confirmed by rendering in a bare app context. Nothing hits it today because
mail always goes out mid-request, but it means **any future attempt to send
mail from a Celery task or a CLI command will crash on the first `_()` in the
template**, not fail quietly in English. That is worth knowing before someone
moves mail sending to a queue, which is the obvious next infrastructure step.

The templates' hardcoded `lang="en"` is therefore not the bug — it is an
accurate description of an email that is usually, but not reliably, English.
`tests/component/test_html_lang.py` pins the list of files allowed to hardcode
it, so this stays visible.

Deciding this needs a product answer, not just a patch:

- **Which language should an invite be in?** The recipient has no account and
  no stored preference at invite time — that is the whole point of an invite.
  Candidates: the assembly's language, the inviting organiser's explicit
  choice at the point of sending, or English as a deliberate lingua franca.
- **Once `User.preferred_language` exists**, mail to an existing user has an
  obvious answer, and step 3 of the chain above stops being dead code. That
  suggests doing the user preference first and revisiting invites after.
- Whatever is chosen, the mechanism is `force_locale` around the render, and
  the `lang` attribute in the five email templates should then be set from the
  same value rather than left literal.

## Suggested order

The user language preference (step 3) is the keystone: it makes mail-to-users
answerable and gives the language switcher somewhere to persist to. Case 1 is
independent of it and is the one currently handing people a form they may not
read, so it is the more urgent of the two. Case 2's invite question can wait
behind the preference field, but the Celery observation should be recorded
wherever the background-task work is planned, since it turns a quiet
English-fallback assumption into a crash.

## What is already done

- `html_lang()` in `extensions.py`, registered as a Jinja global in
  `flask_app.py`, and used by `base.html`, `base_public.html` and
  `backoffice/base.html`.
- `tests/component/test_html_lang.py` renders all three bases under `hu`, `en`
  and `en-GB` — the last because BCP 47 wants `en-GB` where gettext says
  `en_GB`, and a browser ignores an attribute with the underscore.
- The same file pins which templates may hardcode `lang`, so a base added later
  cannot quietly repeat the original mistake.
