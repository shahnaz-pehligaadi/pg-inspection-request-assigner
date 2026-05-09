from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    port: int = 8000
    log_level: str = "INFO"

    inspection_service_url: str
    internal_api_key: str

    default_dry_run: bool = True

    inspection_service_timeout_sec: float = 30.0
    inspection_service_page_size: int = 200

    solver_time_sec: int = 30
    w_assign: int = 1000
    w_urgency: int = 10

    pending_status_id: str = "insp-req-status01"


settings = Settings()  # type: ignore[call-arg]
