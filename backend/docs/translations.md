# Translation Management

OpenDLP uses Flask-Babel for internationalization and localization.

## Current Status

Currently only **Hungarian (`hu`)** translation is available. The default configuration lists `en,es,fr,de` as supported languages, but those translation files have not been created yet.

## Quick Start

1. **Configure languages** in `env` file:

   ```bash
   SUPPORTED_LANGUAGES=en,es,fr,de
   BABEL_DEFAULT_LOCALE=en
   ```

2. **Extract and update catalogues** after adding or changing translatable
   strings:

   ```bash
   just translate-regen
   ```

3. **Initialize a new language** (one-off, before its first
   `just translate-regen`):

   ```bash
   uv run pybabel init -i translations/messages.pot -d translations -l es
   ```

4. **Check the catalogues compile**:

   ```bash
   just translate-check
   ```

5. **Compile translations** to the `.mo` files the application actually reads:

   ```bash
   just translate-compile
   ```

**Use the `just` recipes, not raw `pybabel`.** The recipes carry flags and
arguments that are not optional, and a bare `pybabel` invocation quietly does
the wrong thing:

- `pybabel update` without `--ignore-obsolete` leaves an entry behind for every
  string you delete. Once one of those `#~` entries collides with a live msgid
  it is a duplicate definition, and the catalogue stops compiling altogether.
  This is not hypothetical: it is how the Hungarian catalogue accumulated 873 of
  them.
- `pybabel extract` over `.` alone misses the ~100 msgids the
  `sortition-algorithms` library contributes, and walks `thirdparty/` and
  `.venv/`. `translate-regen` passes the installed library's path as a second
  source argument and excludes both directories.

`pybabel init` in step 3 is the one raw command that is still correct — it
creates a fresh catalogue from the POT and takes no flags we care about. From
then on the new language is picked up by `translate-regen` like any other.

## Translation Workflow

### Adding New Translatable Strings

In Python code:

```python
from opendlp.translations import _, _l

# Use _ for immediate translation
flash(_("Login successful"))

# Use _l for lazy translation (exceptions, etc.)
message = _l("User %(username)s not found", username=user.name)
```

In Jinja2 templates:

```html
<h1>{{ _('Welcome') }}</h1>
<p>{{ _('Hello %(name)s', name=user.name) }}</p>
```

### Managing Translations

The commands are in [Quick Start](#quick-start) above, which is the canonical
list. Don't restate them here: a second copy drifts from the first, and the
copy that drifts is the one somebody follows.

The only step with any human work in it is the middle one: edit the `.po` files
under `translations/[locale]/LC_MESSAGES/messages.po` between
`just translate-regen` and `just translate-check`.

**Important:** The `.mo` (compiled) files must be regenerated after any `.po` file changes for translations to take effect. The application reads from `.mo` files, not `.po` files.

### Directory Structure

```
translations/
├── messages.pot          # Template file with all translatable strings
├── en/
│   └── LC_MESSAGES/
│       ├── messages.po   # English translations (source)
│       └── messages.mo   # Compiled translations
└── es/
    └── LC_MESSAGES/
        ├── messages.po   # Spanish translations
        └── messages.mo   # Compiled translations
```

## Configuration

Languages are configured in `src/opendlp/config.py` via environment variables:

- `SUPPORTED_LANGUAGES`: Comma-separated language codes (default: `en,es,fr,de`)
- `BABEL_DEFAULT_LOCALE`: Default language (default: `en`)
- `BABEL_DEFAULT_TIMEZONE`: Default timezone (default: `UTC`)

## Language Detection

OpenDLP detects user language in this order:

1. URL parameter: `?lang=es`
2. Session preference (persisted across requests)
3. User account language preference (future feature)
4. Browser Accept-Language header
5. Default locale fallback

### The session preference is a cookie

Step 2 stores the language under the `"language"` key inside the Flask session, so it rides on
the 7-day `session` cookie. **This is the only cookie an anonymous front-page visitor can
acquire** — everything else requires them to sign in or open a form.

There is no dedicated language cookie, and adding one would be a decision rather than a
refactor. We rely on the argument that a user who clicks "Español" has explicitly requested
the service of being shown Spanish, which keeps the cookie inside the *strictly necessary*
exception and means we need no consent banner.

If you are changing how the language preference persists — a dedicated cookie, a longer
lifetime, `localStorage` — read [docs/personal-data.md](personal-data.md) first. Step 3, the
future account preference, is a database field rather than a cookie, and raises none of this.

## Further Reading

- [Personal Data](personal-data.md) — cookies, logging, and the right to erasure
- [Flask-Babel Documentation](https://python-babel.github.io/flask-babel/)
- [GNU gettext Manual](https://www.gnu.org/software/gettext/manual/)
- [Babel Documentation](https://babel.pocoo.org/)
- [Python i18n Best Practices](https://docs.python.org/3/library/gettext.html)
