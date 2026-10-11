from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sahaayak"
    environment: str = "development"
    database_url: str
    secret_key: str
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173"
    min_group_size: int = 5  # privacy: suppress aggregate groups smaller than this

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()