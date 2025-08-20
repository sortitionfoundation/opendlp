"""ABOUTME: Configuration management for OpenDLP Flask application
ABOUTME: Loads environment variables and provides configuration objects for different environments"""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

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


@dataclass(slots=True, kw_only=True)
class RedisCfg:
    host: str
    port: int

    def to_url(self) -> str:
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


class FlaskConfig:
    """Base configuration class that loads from environment variables."""

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    TESTING = False

    def __init__(self) -> None:
        self.SQLALCHEMY_DATABASE_URI = get_db_uri()
        self.REDIS_URL = RedisCfg.from_env().to_url()
        self.SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
        self.FLASK_ENV: str = os.environ.get("FLASK_ENV", "development")
        self.DEBUG: bool = to_bool(os.environ.get("DEBUG", "False"), context_str="DEBUG=")

        # Session configuration
        self.SESSION_TYPE = "redis"
        self.SESSION_REDIS = None  # Will be set by Flask-Session

        # Babel/i18n configuration
        self.LANGUAGES = self._get_supported_language_codes()
        self.BABEL_DEFAULT_LOCALE = os.environ.get("BABEL_DEFAULT_LOCALE", "en")
        self.BABEL_DEFAULT_TIMEZONE = os.environ.get("BABEL_DEFAULT_TIMEZONE", "UTC")

        # OAuth configuration
        self.OAUTH_GOOGLE_CLIENT_ID: str = os.environ.get("OAUTH_GOOGLE_CLIENT_ID", "")
        self.OAUTH_GOOGLE_CLIENT_SECRET: str = os.environ.get("OAUTH_GOOGLE_CLIENT_SECRET", "")

        # Selection algorithm configuration
        # 600 is seconds - so 10 minutes
        self.SELECTION_TIMEOUT: int = int(os.environ.get("SELECTION_TIMEOUT", "600"))
        # 168 = 24 * 7 - so 7 days
        self.INVITE_EXPIRY_HOURS: int = int(os.environ.get("INVITE_EXPIRY_HOURS", "168"))

        # Deployment configuration
        self.APPLICATION_ROOT = os.environ.get("APPLICATION_ROOT", "/")

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


class FlaskTestSQLiteConfig(FlaskConfig):
    """Test configuration that uses SQLite in-memory database."""

    TESTING = True
    WTF_CSRF_ENABLED = False

    def __init__(self) -> None:
        super().__init__()
        self.SQLALCHEMY_DATABASE_URI = SQLITE_DB_URI
        self.SECRET_KEY = "test-secret-key-aockgn298zx081238"  # noqa: S105
        self.FLASK_ENV = "testing"
        self.SESSION_TYPE = "filesystem"  # Use filesystem for testing
        session_file_dir = Path(tempfile.gettempdir()) / "flask_session"
        session_file_dir.mkdir(exist_ok=True)
        self.SESSION_FILE_DIR = str(session_file_dir)


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
        # TODO: consider this for all production?
        # self.LOG_TO_STDOUT = True

        # Ensure production has proper secret key
        if self.SECRET_KEY == "dev-secret-key-change-in-production":  # noqa: S105
            raise ValueError("SECRET_KEY must be set in production")


def get_config(config_name: str = "") -> FlaskConfig:
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
