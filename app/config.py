"""환경설정 로더. .env 또는 OS 환경변수에서 읽는다."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="OHN_", extra="ignore")

    # ANTHROPIC_API_KEY는 prefix 예외(공식 SDK 환경변수명 유지)
    anthropic_api_key: str = ""

    model: str = "claude-sonnet-4-6"
    temperature: float = 0.95
    max_group_size: int = 6
    max_pairs: int = 6

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.anthropic_api_key:
            import os
            self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")


settings = Settings()
