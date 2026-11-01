from pydantic_settings import BaseSettings, SettingsConfigDict

class FrontendSettings(BaseSettings):
    API_BASE_URL: str = "http://127.0.0.1:8000"
    API_TIMEOUT: int = 15

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = FrontendSettings()