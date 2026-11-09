from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    # Optional so that tests and non-voice routes run without a key.
    openai_api_key: SecretStr | None = None
    openai_realtime_model: str = "gpt-realtime-2.1"
    shop_timeout_seconds: float = 2.0
    openai_realtime_voice: str = "marin"
    # Mounts the hidden /issues routes for tests and scripts/check_requirements.py.
    enable_dev_api: bool = False
