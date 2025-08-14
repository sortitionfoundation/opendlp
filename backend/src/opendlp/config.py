"""ABOUTME: Configuration management for OpenDLP Flask application
ABOUTME: Loads environment variables and provides configuration objects for different environments"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def get_postgres_uri(default_db_name: str = "opendlp", user: str = "opendlp") -> str:
    host = os.environ.get("DB_HOST", "localhost")
    default_port = 54321 if host == "localhost" else 5432
    port = int(os.environ.get("DB_PORT", default_port))
    password = os.environ.get("DB_PASSWORD", "abc123")
    db_name = os.environ.get("DB_NAME", default_db_name)
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"


def get_api_url() -> str:
    host = os.environ.get("API_HOST", "localhost")
    port = 5005 if host == "localhost" else 80
    return f"http://{host}:{port}"


@dataclass(frozen=True, slots=True, kw_only=True)
class RedisCfg:
    host: str
    port: int

    def to_url(self) -> str:
        return f"redis://{self.host}:{self.port}"

    @classmethod
    def from_env(cls) -> "RedisCfg":
        host = os.environ.get("REDIS_HOST", "localhost")
        port = 63791 if host == "localhost" else 6379
        return RedisCfg(host=host, port=port)


@dataclass(frozen=True, slots=True, kw_only=True)
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
        self.SQLALCHEMY_DATABASE_URI = get_postgres_uri()
        self.REDIS_URL = RedisCfg.from_env().to_url()
        self.SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
        self.FLASK_ENV: str = os.environ.get("FLASK_ENV", "development")
        self.DEBUG: bool = to_bool(os.environ.get("DEBUG", "False"), context_str="DEBUG=")

        # Session configuration
        self.SESSION_TYPE = "redis"
        self.SESSION_REDIS = None  # Will be set by Flask-Session

        # OAuth configuration
        self.OAUTH_GOOGLE_CLIENT_ID: str = os.environ.get("OAUTH_GOOGLE_CLIENT_ID", "")
        self.OAUTH_GOOGLE_CLIENT_SECRET: str = os.environ.get("OAUTH_GOOGLE_CLIENT_SECRET", "")

        # Selection algorithm configuration
        # 600 is seconds - so 10 minutes
        self.SELECTION_TIMEOUT: int = int(os.environ.get("SELECTION_TIMEOUT", "600"))
        # 168 = 24 * 7 - so 7 days
        self.INVITE_EXPIRY_HOURS: int = int(os.environ.get("INVITE_EXPIRY_HOURS", "168"))


class FlaskTestConfig(FlaskConfig):
    """Test configuration that uses SQLite in-memory database."""

    TESTING = True
    WTF_CSRF_ENABLED = False

    def __init__(self) -> None:
        super().__init__()
        self.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        self.SECRET_KEY = "test-secret-key-aockgn298zx081238"  # noqa: S105
        self.FLASK_ENV = "testing"
        self.SESSION_TYPE = "filesystem"  # Use filesystem for testing


class FlaskProductionConfig(FlaskConfig):
    """Production configuration with stricter defaults."""

    def __init__(self) -> None:
        super().__init__()
        self.FLASK_ENV = "production"
        # Ensure production has proper secret key
        if self.SECRET_KEY == "dev-secret-key-change-in-production":  # noqa: S105
            raise ValueError("SECRET_KEY must be set in production")


def get_config(config_name: str = "") -> FlaskConfig:
    """Return the appropriate configuration based on FLASK_ENV or config_name."""
    env = config_name.strip() or os.environ.get("FLASK_ENV", "development")
    env = env.lower().strip()

    config_classes = {
        "development": FlaskConfig,
        "testing": FlaskTestConfig,
        "production": FlaskProductionConfig,
    }

    # Fall back to development if unknown config
    config_cls = config_classes.get(env, FlaskConfig)
    return config_cls()
