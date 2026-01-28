"""ABOUTME: Configuration management for OpenDLP Flask application
ABOUTME: Loads environment variables and provides configuration objects for different environments"""

import base64
import logging
import logging.config
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cachelib.file import FileSystemCache
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


SQLITE_DB_URI = "sqlite:///:memory:"


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
    def from_env(cls, default_db_name: str = "opendlp", user: str = "opendlp") -> "PostgresCfg":
        host = os.environ.get("DB_HOST", "localhost")
        default_port = 54321 if host == "localhost" else 5432
        return PostgresCfg(
            user=user,
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
    db: str = ""

    def to_url(self) -> str:
        if self.db:
            return f"redis://{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}"

    @classmethod
    def from_env(cls) -> "RedisCfg":
        host = os.environ.get("REDIS_HOST", "localhost")
        default_port = 63791 if host == "localhost" else 6379
        port = int(os.environ.get("REDIS_PORT", default_port))
        return RedisCfg(host=host, port=port)


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


class FlaskBaseConfig:
    """Base configuration class that loads from environment variables."""

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    TESTING = False

    def __init__(self) -> None:
        self.SQLALCHEMY_DATABASE_URI = get_db_uri()
        self.SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
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


class FlaskTestSQLiteConfig(FlaskBaseConfig):
    """Test configuration that uses SQLite in-memory database."""

    TESTING = True
    WTF_CSRF_ENABLED = False

    def __init__(self) -> None:
        super().__init__()
        self.SQLALCHEMY_DATABASE_URI = SQLITE_DB_URI
        self.SECRET_KEY = "test-secret-key-aockgn298zx081238"  # noqa: S105
        self.FLASK_ENV = "testing"

        # Use filesystem for session cache for testing
        self.SESSION_TYPE = "cachelib"
        session_file_dir = Path(tempfile.gettempdir()) / "flask_session"
        session_file_dir.mkdir(exist_ok=True)
        self.SESSION_CACHELIB = FileSystemCache(str(session_file_dir))


class FlaskTestPostgresConfig(FlaskTestSQLiteConfig):
    def __init__(self) -> None:
        super().__init__()
        postgres_cfg = PostgresCfg.from_env()
        postgres_cfg.port = 54322
        self.SQLALCHEMY_DATABASE_URI = postgres_cfg.to_url()


class FlaskProductionConfig(FlaskConfig):
    """Production configuration with stricter defaults."""

    def __init__(self) -> None:
        super().__init__()
        self.FLASK_ENV = "production"
        # always override the DEBUG option in production
        self.DEBUG = False
        # TODO: consider this for all production?
        # self.LOG_TO_STDOUT = True

        # Ensure production has proper secret key
        if self.SECRET_KEY == "dev-secret-key-change-in-production":  # noqa: S105
            raise InvalidConfig("SECRET_KEY must be set in production")

        # Ensure production has email adapter configured
        if not os.environ.get("EMAIL_ADAPTER"):
            raise InvalidConfig("EMAIL_ADAPTER must be set in production")


def get_config(config_name: str = "") -> FlaskBaseConfig:
    """Return the appropriate configuration based on FLASK_ENV or config_name."""
    env = config_name.strip() or os.environ.get("FLASK_ENV", "development")
    env = env.lower().strip()

    config_classes = {
        "development": FlaskConfig,
        "testing": FlaskTestSQLiteConfig,
        "testing_postgres": FlaskTestPostgresConfig,
        "testing_sqlite": FlaskTestSQLiteConfig,
        "production": FlaskProductionConfig,
    }

    # Fall back to development if unknown config
    config_cls = config_classes.get(env, FlaskConfig)
    return config_cls()


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


def get_test_csv_data_dir() -> Path:
    """Get directory containing test CSV files (features.csv, candidates.csv)"""
    default_dir = _get_project_root() / "tests" / "csv_fixtures" / "selection_data"
    return Path(os.environ.get("TEST_CSV_DATA_DIR", str(default_dir)))


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
