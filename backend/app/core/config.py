"""Local settings; backend-only hosted-service credentials stay secret."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / '.env', extra='ignore', hide_input_in_errors=True
    )

    app_env: Literal['development', 'test'] = 'development'
    database_diagnostics_enabled: bool = False
    backend_host: str = '127.0.0.1'
    backend_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: str = 'http://localhost:5173'
    supabase_url: str = ''
    supabase_publishable_key: SecretStr = SecretStr('')
    analysis_max_characters: int = Field(default=20000, ge=100, le=20000)
    analysis_max_tokens: int = Field(default=4096, ge=50, le=4096)
    gemini_api_key: SecretStr = SecretStr('')
    robustness_signing_key: SecretStr = SecretStr('')
    robustness_signing_key_id: str = 'v1'
    gemini_model: str = 'gemini-3.8-flash'
    gemini_timeout_seconds: float = Field(default=45, ge=1, le=120)
    gemini_max_output_tokens: int = Field(default=2048, ge=256, le=4096)
    gemini_min_interval_seconds: float = Field(default=5, ge=0, le=60)

    @field_validator('supabase_publishable_key')
    @classmethod
    def validate_publishable_key(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value() and not value.get_secret_value().startswith('sb_publishable_'):
            raise ValueError('Use a Supabase publishable key; privileged or legacy keys are not accepted')
        return value

    @field_validator('supabase_url')
    @classmethod
    def validate_supabase_url(cls, value: str) -> str:
        if not value:
            return value
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            raise ValueError('Supabase URL must be an HTTPS project origin')
        return value.rstrip('/')

    @field_validator('cors_origins')
    @classmethod
    def validate_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(',')]
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in ('http', 'https')
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or '*' in origin
            ):
                raise ValueError('CORS_ORIGINS must contain explicit HTTP(S) origins without paths')
            try:
                parsed.port
            except ValueError as error:
                raise ValueError('Invalid CORS origin port') from error
        return ','.join(origins)

    @property
    def allowed_origins(self) -> list[str]:
        return self.cors_origins.split(',')
