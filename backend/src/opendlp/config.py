"""ABOUTME: Configuration management for OpenDLP Flask application
ABOUTME: Loads environment variables and provides configuration objects for different environments"""

import base64
import logging
import logging.config
import os
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from functools import cache
from pathlib import Path

import sortition_algorithms.settings
from cachelib.base import BaseCache
from cachelib.file import FileSystemCache
from cachelib.simple import SimpleCache
from dotenv import load_dotenv
from redis import Redis

load_dotenv()


class InvalidConfig(Exception):
    """Error for when the config is not valid"""


def is_production() -> bool:
    flask_env = os.environ.get("FLASK_ENV", "development")
    return flask_env == "production"


def is_development() -> bool:
    flask_env = os.environ.get("FLASK_ENV", "development")
    return flask_env == "development"


def get_log_level() -> int:
    log_level_str = os.environ.get("LOG_LEVEL", "INFO")
    return logging.getLevelNamesMapping().get(log_level_str, logging.INFO)


def should_log_all_requests() -> bool:
    return is_production() and bool_environ_get("LOG_ALL_REQUESTS")


def get_secret_key() -> str:
    """Return the application secret key (env-backed, app-context independent)."""
    return os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")


@dataclass(slots=True, kw_only=True)
class PostgresCfg:
    user: str
    password: str
    host: str
    port: int
    db_name: str

    def to_url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db_name}"

    @classmethod
    def from_env(cls, default_db_name: str = "opendlp", default_user: str = "opendlp") -> "PostgresCfg":
        host = os.environ.get("DB_HOST", "localhost")
        default_port = 54321 if host == "localhost" else 5432
        return PostgresCfg(
            user=os.environ.get("DB_USER", default_user),
            password=os.environ.get("DB_PASSWORD", "abc123"),
            host=host,
            port=int(os.environ.get("DB_PORT", default_port)),
            db_name=os.environ.get("DB_NAME", default_db_name),
        )


def get_db_uri() -> str:
    return os.environ.get("DB_URI", PostgresCfg.from_env().to_url())


def get_api_url() -> str:
    host = os.environ.get("API_HOST", "localhost")
    port = 5005 if host == "localhost" else 80
    return f"http://{host}:{port}"


def get_google_auth_json_path() -> Path:
    return Path(os.environ.get("GOOGLE_AUTH_JSON_PATH", "/no-such-file"))


@dataclass(slots=True, kw_only=True)
class RedisCfg:
    host: str
    port: int
    db: int = 0

    def to_url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"

    @classmethod
    def from_env(cls) -> "RedisCfg":
        host = os.environ.get("REDIS_HOST", "localhost")
        default_port = 63791 if host == "localhost" else 6379
        port = int(os.environ.get("REDIS_PORT", default_port))
        db = int(os.environ.get("REDIS_DB", "0"))
        return RedisCfg(host=host, port=port, db=db)


@dataclass(slots=True, kw_only=True)
class EmailCfg:
    host: str
    port: int
    http_port: int

    @classmethod
    def get(cls) -> "EmailCfg":
        host = os.environ.get("EMAIL_HOST", "localhost")
        port = 11025 if host == "localhost" else 1025
        http_port = 18025 if host == "localhost" else 8025
        return EmailCfg(host=host, port=port, http_port=http_port)


@dataclass(slots=True, kw_only=True)
class SMTPEmailCfg:
    """SMTP email adapter configuration."""

    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    from_email: str
    from_name: str

    @classmethod
    def from_env(cls) -> "SMTPEmailCfg":
        """Load SMTP configuration from environment variables."""
        return SMTPEmailCfg(
            host=os.environ.get("SMTP_HOST", ""),
            port=int(os.environ.get("SMTP_PORT", "587")),
            username=os.environ.get("SMTP_USERNAME", ""),
            password=os.environ.get("SMTP_PASSWORD", ""),
            use_tls=bool_environ_get("SMTP_USE_TLS", True),
            from_email=os.environ.get("SMTP_FROM_EMAIL", ""),
            from_name=os.environ.get("SMTP_FROM_NAME", ""),
        )


def to_bool(value: str | None, context_str: str = "") -> bool:
    """
    Convert string to boolean. Valid options (after stripping whitespace and making lower-case)
    - False: "false", "no", "off", "0", None, ""
    - True: "true", "yes", "on", "1"

    The `context_str` is there for the error message, to help find the issue.
    """
    if value is None:
        return False
    value = value.lower().strip()
    if value in ("false", "no", "off", "0", ""):
        return False
    if value in ("true", "yes", "on", "1"):
        return True
    raise ValueError(
        f"Cannot convert '{context_str}{value}' to boolean. Valid values are: true/false, 1/0, yes/no, on/off (case-insensitive)"
    )


def bool_environ_get(env_key: str, default: bool = False) -> bool:
    """Get environment variable and convert to bool. Default is false if not found."""
    default_str = "true" if default else "false"
    return to_bool(os.environ.get(env_key, default_str), context_str=f"{env_key}=")


def get_max_csv_upload_mb() -> int:
    """Maximum allowed size for an uploaded respondent CSV, in megabytes.

    Default 50 MB. Real production CSVs sit comfortably under 2 MB so 50 MB
    leaves generous headroom. Bounded to [1, 500] — values outside the range
    are clamped and a warning is logged so the operator sees the override.

    Environment variable: ``MAX_CSV_UPLOAD_MB``.
    """
    return _clamped_int_env("MAX_CSV_UPLOAD_MB", 50, 1, 500)


def get_max_csv_upload_bytes() -> int:
    """Convenience: ``get_max_csv_upload_mb()`` expressed in bytes."""
    return get_max_csv_upload_mb() * 1024 * 1024


def get_task_timeout_hours() -> int:
    """
    Get task timeout in hours from environment.
    Returns 24 (hours) as default if not set or invalid.

    Environment variable: TASK_TIMEOUT_HOURS
    """
    timeout_str = os.environ.get("TASK_TIMEOUT_HOURS", "")
    if not timeout_str:
        return 24

    try:
        timeout = int(timeout_str)
        if timeout <= 0:
            logging.warning(f"TASK_TIMEOUT_HOURS must be positive, got '{timeout_str}'. Using default 24 hours.")
            return 24
        return timeout
    except ValueError:
        logging.warning(f"Invalid TASK_TIMEOUT_HOURS value '{timeout_str}'. Using default 24 hours.")
        return 24


# Bounds for registration page HTML size limits. The minimum keeps a published
# page from being trivially small; the ceiling guards against runaway storage.
_REGISTRATION_HTML_MIN_BYTES = 1024
_REGISTRATION_HTML_MAX_BYTES = 10 * 1024 * 1024


def _registration_html_max_bytes(env_key: str, default: int) -> int:
    """Read a registration page HTML byte limit from the environment.

    Falls back to ``default`` on a missing or invalid value, and clamps to
    [1 KB, 10 MB] with a logged warning so an operator sees the override.
    """
    return _clamped_int_env(env_key, default, _REGISTRATION_HTML_MIN_BYTES, _REGISTRATION_HTML_MAX_BYTES)


def get_registration_form_html_max_bytes() -> int:
    """Maximum allowed size for a registration page's form HTML, in bytes.

    Default 200 KB. Bounded to [1 KB, 10 MB]. Environment variable:
    ``REGISTRATION_FORM_HTML_MAX_BYTES``.
    """
    return _registration_html_max_bytes("REGISTRATION_FORM_HTML_MAX_BYTES", 204800)


def get_registration_thank_you_html_max_bytes() -> int:
    """Maximum allowed size for a registration page's thank-you HTML, in bytes.

    Default 50 KB. Bounded to [1 KB, 10 MB]. Environment variable:
    ``REGISTRATION_THANK_YOU_HTML_MAX_BYTES``.
    """
    return _registration_html_max_bytes("REGISTRATION_THANK_YOU_HTML_MAX_BYTES", 51200)


def get_email_template_body_max_bytes() -> int:
    """Maximum allowed size for an email template's HTML body, in bytes.

    Default 200 KB. Bounded to [1 KB, 10 MB]. Environment variable:
    ``EMAIL_TEMPLATE_BODY_MAX_BYTES``.
    """
    return _registration_html_max_bytes("EMAIL_TEMPLATE_BODY_MAX_BYTES", 204800)


def _clamped_int_env(env_key: str, default: int, minimum: int, maximum: int) -> int:
    """Read an integer from the environment, falling back to ``default`` on a
    missing or invalid value and clamping to [minimum, maximum] with a logged
    warning so an operator sees the override."""
    raw = os.environ.get(env_key, "")
    if not raw:
        return default

    try:
        value = int(raw)
    except ValueError:
        logging.warning(f"Invalid {env_key} value '{raw}'. Using default {default}.")
        return default

    if value < minimum:
        logging.warning(f"{env_key}={value} is below the minimum ({minimum}). Using {minimum}.")
        return minimum
    if value > maximum:
        logging.warning(f"{env_key}={value} is above the hard ceiling ({maximum}). Using {maximum}.")
        return maximum
    return value


def get_max_image_upload_mb() -> int:
    """Maximum allowed size for an uploaded registration image, in megabytes.

    Default 10 MB (phone photos can exceed 5 MB; we downscale afterwards).
    Bounded to [1, 25]. Environment variable: ``MAX_IMAGE_UPLOAD_MB``.
    """
    return _clamped_int_env("MAX_IMAGE_UPLOAD_MB", 10, 1, 25)


def get_max_image_upload_bytes() -> int:
    """Convenience: ``get_max_image_upload_mb()`` expressed in bytes."""
    return get_max_image_upload_mb() * 1024 * 1024


# Register every per-upload-type limit here so get_max_content_length() stays
# correct automatically. Add a new entry whenever a new upload type is introduced.
_UPLOAD_SIZE_CONTRIBUTORS: list[Callable[[], int]] = [
    get_max_csv_upload_bytes,
    get_max_image_upload_bytes,
    get_registration_form_html_max_bytes,
    get_registration_thank_you_html_max_bytes,
]


def get_max_content_length() -> int:
    """Flask MAX_CONTENT_LENGTH: the largest request body any endpoint accepts.

    Derived as the maximum of all per-upload-type limits so the WSGI gateway
    rejects obviously oversized requests while each route still enforces its own
    tighter limit. Add new upload types to ``_UPLOAD_SIZE_CONTRIBUTORS`` above.
    """
    return max(f() for f in _UPLOAD_SIZE_CONTRIBUTORS)


def get_registration_image_max_edge_px() -> int:
    """Maximum length of a registration image's longest edge, in pixels.

    Larger uploads are downscaled to this. Default 2048 (banner width).
    Bounded to [256, 4096]. Environment variable: ``REGISTRATION_IMAGE_MAX_EDGE_PX``.
    """
    return _clamped_int_env("REGISTRATION_IMAGE_MAX_EDGE_PX", 2048, 256, 4096)


def get_max_images_per_registration_page() -> int:
    """Maximum number of images stored per registration page.

    Default 10. Bounded to [1, 50]. Environment variable:
    ``MAX_IMAGES_PER_REGISTRATION_PAGE``.
    """
    return _clamped_int_env("MAX_IMAGES_PER_REGISTRATION_PAGE", 10, 1, 50)


def _get_monitor_uuid_env(env_key: str) -> "uuid.UUID | None":
    value = os.environ.get(env_key, "").strip()
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        logging.warning(f"Invalid {env_key} value '{value}'. Monitoring will be disabled.")
        return None


def get_monitor_assembly_id() -> "uuid.UUID | None":
    """
    Get the UUID of the monitor assembly from the environment.
    Returns None if unset or invalid (monitoring disabled).

    Environment variable: MONITOR_ASSEMBLY_ID
    """
    return _get_monitor_uuid_env("MONITOR_ASSEMBLY_ID")


def get_monitor_user_id() -> "uuid.UUID | None":
    """
    Get the UUID of the monitor user from the environment.
    Returns None if unset or invalid (monitoring disabled).

    Environment variable: MONITOR_USER_ID
    """
    return _get_monitor_uuid_env("MONITOR_USER_ID")


def get_monitor_health_max_age_minutes() -> int:
    """
    Get the maximum age (in minutes) of a successful monitor run before it
    is considered STALE. Returns 45 by default (three 15-minute run cycles).

    Environment variable: MONITOR_HEALTH_MAX_AGE_MINUTES
    """
    value = os.environ.get("MONITOR_HEALTH_MAX_AGE_MINUTES", "")
    if not value:
        return 45
    try:
        parsed = int(value)
        if parsed <= 0:
            logging.warning(
                f"MONITOR_HEALTH_MAX_AGE_MINUTES must be positive, got '{value}'. Using default 45 minutes."
            )
            return 45
        return parsed
    except ValueError:
        logging.warning(f"Invalid MONITOR_HEALTH_MAX_AGE_MINUTES value '{value}'. Using default 45 minutes.")
        return 45


class FlaskBaseConfig:
    """Base configuration class that loads from environment variables."""

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    # Registration form-timing bot check. Gated separately from CSRF so it can
    # be exercised in tests without a CSRF round-trip. Disabled in the test
    # config (see FlaskTestConfig) like WTF_CSRF_ENABLED.
    REGISTRATION_TIMING_CHECK_ENABLED = True
    # Don't expire CSRF tokens on a separate short clock; tie their validity to
    # the session instead. This avoids the common "form expired" 400 error when
    # a user leaves a page open longer than the default one hour.
    WTF_CSRF_TIME_LIMIT = None
    # How long a session (and thus a CSRF token) remains valid.
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    TESTING = False

    def __init__(self) -> None:
        self.SQLALCHEMY_DATABASE_URI = get_db_uri()
        self.SECRET_KEY: str = get_secret_key()
        self.FLASK_ENV: str = os.environ.get("FLASK_ENV", "development")
        self.DEBUG: bool = bool_environ_get("DEBUG")

        # Babel/i18n configuration
        self.LANGUAGES = self._get_supported_language_codes()
        self.BABEL_DEFAULT_LOCALE = os.environ.get("BABEL_DEFAULT_LOCALE", "en")
        self.BABEL_DEFAULT_TIMEZONE = os.environ.get("BABEL_DEFAULT_TIMEZONE", "UTC")
        self.BABEL_TRANSLATION_DIRECTORIES = str(get_translations_path())

        # OAuth configuration
        self.OAUTH_GOOGLE_CLIENT_ID: str = os.environ.get("OAUTH_GOOGLE_CLIENT_ID", "")
        self.OAUTH_GOOGLE_CLIENT_SECRET: str = os.environ.get("OAUTH_GOOGLE_CLIENT_SECRET", "")
        self.OAUTH_MICROSOFT_CLIENT_ID: str = os.environ.get("OAUTH_MICROSOFT_CLIENT_ID", "")
        self.OAUTH_MICROSOFT_CLIENT_SECRET: str = os.environ.get("OAUTH_MICROSOFT_CLIENT_SECRET", "")
        # Optional: Microsoft client secret expiry date for monitoring (format: YYYY-MM-DD)
        self.OAUTH_MICROSOFT_CLIENT_SECRET_EXPIRY: str = os.environ.get("OAUTH_MICROSOFT_CLIENT_SECRET_EXPIRY", "")

        # Email configuration
        # Valid values: "smtp", "console"
        self.EMAIL_ADAPTER: str = os.environ.get("EMAIL_ADAPTER", "console")

        # Site banner configuration (for demo/staging environments)
        # If SITE_BANNER_TEXT is empty (default), no banner is shown
        self.SITE_BANNER_TEXT: str = os.environ.get("SITE_BANNER_TEXT", "")
        # Colour for the banner background (e.g. "yellow", "#ffdd00")
        self.SITE_BANNER_COLOUR: str = os.environ.get("SITE_BANNER_COLOUR", "yellow")

        # Selection algorithm configuration
        # 168 = 24 * 7 - so 7 days
        self.INVITE_EXPIRY_HOURS: int = int(os.environ.get("INVITE_EXPIRY_HOURS", "168"))

        # Support configuration
        self.SUPPORT_EMAIL: str = os.environ.get("SUPPORT_EMAIL", "opendlp-support@sortitionfoundation.org")

        # External help site URLs
        self.HELP_SITE_HOME: str = os.environ.get("HELP_SITE_HOME", "https://docs.sortitionlab.org/help/")
        self.HELP_SITE_DATA_AGREEMENT: str = os.environ.get(
            "HELP_SITE_DATA_AGREEMENT", "https://docs.sortitionlab.org/data-and-legal/data-agreement/"
        )
        self.HELP_SITE_COOKIES: str = os.environ.get(
            "HELP_SITE_COOKIES", "https://docs.sortitionlab.org/data-and-legal/cookies/"
        )

        # Login rate limiting
        self.LOGIN_RATE_LIMIT_PER_EMAIL: int = int(os.environ.get("LOGIN_RATE_LIMIT_PER_EMAIL", "5"))
        self.LOGIN_RATE_LIMIT_PER_IP: int = int(os.environ.get("LOGIN_RATE_LIMIT_PER_IP", "20"))
        self.LOGIN_RATE_LIMIT_WINDOW_MINUTES: int = int(os.environ.get("LOGIN_RATE_LIMIT_WINDOW_MINUTES", "15"))

        # Registration bot protection
        self.REGISTRATION_RATE_LIMIT_PER_IP: int = int(os.environ.get("REGISTRATION_RATE_LIMIT_PER_IP", "30"))
        self.REGISTRATION_RATE_LIMIT_PER_EMAIL: int = int(os.environ.get("REGISTRATION_RATE_LIMIT_PER_EMAIL", "5"))
        self.REGISTRATION_RATE_LIMIT_IP_WINDOW_MINUTES: int = int(
            os.environ.get("REGISTRATION_RATE_LIMIT_IP_WINDOW_MINUTES", "60")
        )
        self.REGISTRATION_RATE_LIMIT_EMAIL_WINDOW_MINUTES: int = int(
            os.environ.get("REGISTRATION_RATE_LIMIT_EMAIL_WINDOW_MINUTES", "1440")
        )
        self.REGISTRATION_MIN_FILL_SECONDS: int = int(os.environ.get("REGISTRATION_MIN_FILL_SECONDS", "3"))

        # File upload limit — the maximum across all per-upload-type limits so
        # the WSGI layer rejects obviously oversized requests before allocating
        # memory. Each route still enforces its own tighter limit.
        self.MAX_CONTENT_LENGTH = get_max_content_length()

        # Deployment configuration
        self.APPLICATION_ROOT = os.environ.get("APPLICATION_ROOT", "/")
        # Server name for URL generation (used when behind a reverse proxy)
        # Format: "domain.com" or "domain.com:port"
        # If we use the empty string then we get no host, even though the logic seems
        # to only check for truthiness
        self.SERVER_NAME: str | None = os.environ.get("SERVER_NAME", None)

    def _get_supported_language_codes(self) -> list[str]:
        """Get list of supported language codes from environment or default."""
        languages_env = os.environ.get("SUPPORTED_LANGUAGES", "en,es,fr,de")
        languages = [lang.strip() for lang in languages_env.split(",") if lang.strip()]
        # Ensure we always have at least English as a fallback
        return languages if languages else ["en"]

    def get_supported_languages(self) -> list[tuple[str, str]]:
        """Get list of supported languages as (code, name) tuples."""
        # Language code to name mapping
        language_names = {
            "en": "English",
            "es": "Español",
            "fr": "Français",
            "de": "Deutsch",
            "hu": "Magyar",
            "it": "Italiano",
            "pt": "Português",
            "ru": "Русский",
            "zh": "中文",
            "ja": "日本語",
            "ko": "한국어",
            "ar": "العربية",
            "hi": "हिन्दी",
        }

        return [(code, language_names.get(code, code.upper())) for code in self.LANGUAGES]


class FlaskConfig(FlaskBaseConfig):
    def __init__(self) -> None:
        super().__init__()
        # Session configuration
        redis_cfg = RedisCfg.from_env()
        self.SESSION_TYPE = "redis"
        self.SESSION_REDIS = Redis(host=redis_cfg.host, port=redis_cfg.port)


class FlaskTestConfig(FlaskBaseConfig):
    """Test configuration that uses PostgreSQL test database."""

    TESTING = True
    WTF_CSRF_ENABLED = False
    REGISTRATION_TIMING_CHECK_ENABLED = False

    def __init__(self) -> None:
        super().__init__()
        if not os.environ.get("DB_URI"):
            postgres_cfg = PostgresCfg.from_env()
            postgres_cfg.port = 54322
            self.SQLALCHEMY_DATABASE_URI = postgres_cfg.to_url()
        self.SECRET_KEY = "test-secret-key-aockgn298zx081238"  # noqa: S105  # pragma: allowlist secret
        self.FLASK_ENV = "testing"

        # Use filesystem for session cache for testing
        # Namespace by xdist worker to avoid collisions during parallel runs
        self.SESSION_TYPE = "cachelib"
        worker_suffix = os.environ.get("PYTEST_XDIST_WORKER", "")
        session_dir_name = f"flask_session_{worker_suffix}" if worker_suffix else "flask_session"
        session_file_dir = Path(tempfile.gettempdir()) / session_dir_name
        session_file_dir.mkdir(exist_ok=True)
        self.SESSION_CACHELIB: BaseCache = FileSystemCache(str(session_file_dir))


class FlaskTestComponentConfig(FlaskTestConfig):
    """Test configuration for component tests: in-memory sessions, no external services.

    Component tests drive the Flask app against a FakeUnitOfWork, so they need no
    PostgreSQL and no Redis. Sessions use an in-memory cachelib backend so login
    works without touching disk or a session server.
    """

    def __init__(self) -> None:
        super().__init__()
        self.SESSION_CACHELIB = SimpleCache()


class FlaskProductionConfig(FlaskConfig):
    """Production configuration with stricter defaults."""

    def __init__(self) -> None:
        super().__init__()
        self.FLASK_ENV = "production"
        # always override the DEBUG option in production
        self.DEBUG = False
        # cookie settings
        self.SESSION_COOKIE_SECURE = True
        self.SESSION_COOKIE_SAMESITE = "Lax"  # Lax required for OAuth flows (allows cookies on top-level navigation)
        # remember cookie settings - for flask-login "remember me" functionality
        self.REMEMBER_COOKIE_SECURE = True
        self.REMEMBER_COOKIE_SAMESITE = "Lax"  # Lax required for OAuth flows
        self.REMEMBER_COOKIE_DURATION = timedelta(days=7)
        # TODO: consider this for all production?
        # self.LOG_TO_STDOUT = True

        # Ensure production has proper secret key
        if self.SECRET_KEY == "dev-secret-key-change-in-production":  # noqa: S105  # pragma: allowlist secret
            raise InvalidConfig("SECRET_KEY must be set in production")

        # Ensure production has email adapter configured. The console adapter
        # prints raw recipient addresses to stdout, bypassing log redaction, so
        # it must not be used in production.
        if not os.environ.get("EMAIL_ADAPTER"):
            raise InvalidConfig("EMAIL_ADAPTER must be set in production")
        if self.EMAIL_ADAPTER == "console":
            raise InvalidConfig("EMAIL_ADAPTER must not be 'console' in production (it logs recipient PII to stdout)")


def get_config(config_name: str = "") -> FlaskBaseConfig:
    """Return the appropriate configuration based on FLASK_ENV or config_name."""
    env = config_name.strip() or os.environ.get("FLASK_ENV", "development")
    env = env.lower().strip()

    config_classes = {
        "development": FlaskConfig,
        "testing": FlaskTestConfig,
        "testing_postgres": FlaskTestConfig,
        "testing_component": FlaskTestComponentConfig,
        "production": FlaskProductionConfig,
    }

    # Fall back to development if unknown config
    config_cls = config_classes.get(env, FlaskConfig)
    return config_cls()


@cache
def _get_project_root() -> Path:
    # Get project root - go up from src/opendlp/entrypoints/flask_app.py to project root
    # But if installed in venv (as in production) then use PROJECT_ROOT
    required_sub_dirs = ("static", "templates", "translations")

    def _is_valid_project_root(path: Path) -> bool:
        return path.is_dir() and all((path / sub_dir).is_dir() for sub_dir in required_sub_dirs)

    # this is in order of priority to use
    # 1. explicitly set by environment variable
    # 2. editable install or direct run - so relative within the git repo
    # 3. inferred when running in github actions
    # 4. current working directory (eg. running tests)
    possible_roots = (
        Path(os.environ.get("PROJECT_ROOT", "/non-existent")),
        Path(__file__).parents[3],
        Path(os.environ.get("GITHUB_WORKSPACE", "/non-existent")) / "backend",
        Path.cwd(),
    )
    valid_roots = [p for p in possible_roots if _is_valid_project_root(p)]
    if not valid_roots:
        raise InvalidConfig(
            f"Could not find project root containing required directories: {' '.join(required_sub_dirs)}"
        )
    return valid_roots[0]


def get_templates_path() -> Path:
    return _get_project_root() / "templates"


def get_static_path() -> Path:
    return _get_project_root() / "static"


def get_translations_path() -> Path:
    return _get_project_root() / "translations"


def get_opendlp_version_path() -> Path:
    return _get_project_root() / "generated_version.txt"


def get_git_dir_path() -> Path:
    return (_get_project_root() / ".." / ".git").resolve()


def use_csv_data_source_for_testing() -> bool:
    """Check if we should use CSV instead of Google Sheets (for testing)"""
    return bool_environ_get("USE_CSV_DATA_SOURCE")


def get_csv_test_data_dir() -> Path:
    """Get directory containing test CSV files (features.csv, candidates.csv)"""
    default_dir = _get_project_root() / "tests" / "csv_fixtures" / "selection_data"
    return Path(os.environ.get("CSV_TEST_DATA_DIR", str(default_dir)))


def get_totp_encryption_key() -> bytes:
    """Get the master encryption key from environment.

    Raises:
        ValueError: If TOTP_ENCRYPTION_KEY is not set
    """
    key_str = os.environ.get("TOTP_ENCRYPTION_KEY", "")
    if not key_str:
        raise ValueError("TOTP_ENCRYPTION_KEY environment variable must be set for 2FA to work")

    try:
        return base64.b64decode(key_str)
    except Exception as e:
        raise ValueError(f"TOTP_ENCRYPTION_KEY must be a valid base64-encoded 32-byte key: {e}") from e


def get_solver_backend() -> str:
    """Get the solver backend for sortition-algorithms.

    Returns the solver backend to use. Valid values are 'mip' (CBC) or 'highspy' (HiGHS).

    Configuration priority:
    1. SOLVER_BACKEND environment variable if set
    2. Platform-specific default:
       - macOS (Darwin): 'highspy' (CBC has issues on Apple Silicon)
       - Other platforms: 'mip' (faster in production)

    Environment variable: SOLVER_BACKEND
    """
    env_value = os.environ.get("SOLVER_BACKEND", "").strip().lower()
    if env_value:
        if env_value not in sortition_algorithms.settings.SOLVER_BACKENDS:
            logging.warning(
                f"Invalid SOLVER_BACKEND value '{env_value}'. Must be one of "
                f"({','.join(sortition_algorithms.settings.SOLVER_BACKENDS)}). Using platform default."
            )
        else:
            return env_value

    # Platform-specific default - Macs are particularly bad on cbc, so if we switch
    # the default back to CBC, and Macs are still affected, we will have to
    # have the `if platform.system() == "Darwin": return "highspy"` bit reinstated.

    # CBC does occasionally crash, so we default to highspy as that is more reliable
    return "highspy"
