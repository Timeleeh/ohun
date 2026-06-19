"""환경설정 로더. .env 또는 OS 환경변수에서 읽는다."""
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env를 OS 환경으로 로드 → ANTHROPIC_API_KEY(접두사 없는 키)도 인식됨.
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="OHN_", extra="ignore")

    # 공식 SDK 환경변수명을 그대로 쓰는 키들(접두사 예외, __init__에서 OS 환경으로 보강)
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    # provider: auto | gemini | anthropic | mock (auto = 가진 키 우선순위로 자동 선택)
    provider: str = "auto"
    model: str = "claude-sonnet-4-6"          # Anthropic 모델
    gemini_model: str = "gemini-2.5-flash"    # Gemini 모델 (무료 티어 쿼터 있는 모델)
    temperature: float = 0.95
    max_group_size: int = 6
    max_pairs: int = 6

    # Supabase (없으면 인메모리 store 사용)
    supabase_url: str = ""
    supabase_key: str = ""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        import os
        if not self.anthropic_api_key:
            self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.gemini_api_key:
            self.gemini_api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
        if not self.supabase_url:
            self.supabase_url = os.environ.get("SUPABASE_URL", "")
        if not self.supabase_key:
            self.supabase_key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY", "")


settings = Settings()
