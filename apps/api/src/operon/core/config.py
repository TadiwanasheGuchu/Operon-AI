"""Application settings, loaded from environment variables (prefix ``OPERON_``)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Development-only encryption key. Production startup refuses to run with it.
DEV_SECRET_KEYS = "v1:b3Blcm9uLWRldmVsb3BtZW50LWtleS1ub3QtcHJvZCE="  # noqa: S105 — public dev key, refused in production


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPERON_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "staging", "production"] = "development"
    service_name: str = "operon-api"
    version: str = "0.1.0"

    # Runtime connection uses the least-privilege application role (no BYPASSRLS).
    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://operon_app:operon_app_dev@localhost:5432/operon")
    )
    # Migrations run as the schema owner. Never used by the running application.
    migrations_database_url: SecretStr = SecretStr(
        "postgresql+psycopg://operon_owner:operon_owner_dev@localhost:5432/operon"
    )
    database_pool_size: int = 10
    redis_url: RedisDsn = Field(default=RedisDsn("redis://localhost:6379/0"))

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True
    # Health dependency checks must answer quickly so orchestrators don't pile up probes.
    health_check_timeout_seconds: float = 2.0

    # Public URL of the web app, used to build links in emails.
    web_base_url: str = "http://localhost:3000"

    # Encryption keys for secrets at rest (MFA secrets now; integration credentials in Phase 3).
    # Format "<key_id>:<base64 32-byte key>", comma-separated; the first key encrypts, all decrypt.
    secret_keys: SecretStr = SecretStr(DEV_SECRET_KEYS)

    # Sessions (ADR 0001): opaque token in an HttpOnly cookie, hashed at rest.
    session_cookie_name: str = "operon_session"
    csrf_cookie_name: str = "operon_csrf"
    mfa_cookie_name: str = "operon_mfa"
    cookie_secure: bool | None = None  # None → secure everywhere except development/test
    session_idle_minutes: int = 60
    session_absolute_hours: int = 12

    verification_token_hours: int = 24
    password_reset_token_minutes: int = 30
    invitation_days: int = 7
    mfa_challenge_minutes: int = 5

    # Argon2id parameters (OWASP-recommended baseline). Tests lower memory for speed.
    password_hash_time_cost: int = 3
    password_hash_memory_kib: int = 65536
    password_hash_parallelism: int = 2

    email_backend: Literal["console", "smtp", "memory"] = "console"
    email_from: str = "Operon <no-reply@operon.local>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False

    # Integrations and background work (ADR 0003, ADR 0010).
    # "inline" runs syncs in-process (development/test only); "temporal" starts durable workflows.
    workflow_backend: Literal["temporal", "inline"] = "inline"
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "integrations"
    sync_interval_minutes: int = 15
    # Allow integration URLs on private networks (a local Odoo). Never outside development/test.
    allow_private_integration_hosts: bool = False
    integration_http_timeout_seconds: float = 30.0
    max_upload_bytes: int = 5 * 1024 * 1024

    # Model providers (ADR 0006, ADR 0011). A provider is available only when its key is set;
    # organisations opt in separately. Keys live in the environment / secret manager only.
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5-5"
    openai_api_key: SecretStr | None = None
    # No default: choose the model deliberately when enabling OpenAI.
    openai_model: str | None = None
    ai_timeout_seconds: float = 60.0
    ai_max_output_tokens: int = 4000
    # In-process periodic jobs (incident escalation) when workflow_backend is "inline".
    # 0 disables them (tests drive the jobs directly).
    inline_maintenance_interval_seconds: int = 60

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def secure_cookies(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.environment not in ("development", "test")

    @model_validator(mode="after")
    def _production_safety(self) -> "Settings":
        if self.environment in ("staging", "production"):
            if self.secret_keys.get_secret_value() == DEV_SECRET_KEYS:
                raise ValueError("OPERON_SECRET_KEYS must be set outside development and test.")
            if self.cookie_secure is False:
                raise ValueError("Cookies must be Secure outside development and test.")
            if self.workflow_backend != "temporal":
                raise ValueError(
                    "OPERON_WORKFLOW_BACKEND must be 'temporal' outside development and test."
                )
            if self.allow_private_integration_hosts:
                raise ValueError(
                    "Private integration hosts are only allowed in development and test."
                )
            if self.email_backend != "smtp":
                raise ValueError(
                    "OPERON_EMAIL_BACKEND must be 'smtp' outside development and test."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
