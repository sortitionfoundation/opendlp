# Translation Management

OpenDLP uses Flask-Babel for internationalization and localization.

## Quick Start

1. **Configure languages** in `env` file:

   ```bash
   SUPPORTED_LANGUAGES=en,es,fr,de
   BABEL_DEFAULT_LOCALE=en
   ```

2. **Extract messages** to create/update POT file:

   ```bash
   uv run pybabel extract -F babel.cfg -k _l -o translations/messages.pot .
   ```

3. **Initialize new language**:

   ```bash
   uv run pybabel init -i translations/messages.pot -d translations -l es
   ```

4. **Update existing translations**:

   ```bash
   uv run pybabel update -i translations/messages.pot -d translations
   ```

5. **Compile translations**:

   ```bash
   uv run pybabel compile -d translations
   ```

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

1. **Extract new strings**: Run `pybabel extract` after adding translatable strings
2. **Update PO files**: Run `pybabel update` to merge new strings into existing translations
3. **Translate**: Edit `.po` files in `translations/[locale]/LC_MESSAGES/messages.po`
4. **Compile**: Run `pybabel compile` to generate `.mo` files for production

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

## Further Reading

- [Flask-Babel Documentation](https://python-babel.github.io/flask-babel/)
- [GNU gettext Manual](https://www.gnu.org/software/gettext/manual/)
- [Babel Documentation](https://babel.pocoo.org/)
- [Python i18n Best Practices](https://docs.python.org/3/library/gettext.html)

