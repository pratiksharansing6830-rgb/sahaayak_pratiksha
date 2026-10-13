from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

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
    @model_validator(mode="after")
    def production_needs_real_secret(self):
        if self.environment.lower() == "production" and (
            len(self.secret_key) < 32 or self.secret_key.upper().startswith("CHANGE_ME")
        ):
            raise ValueError("SECRET_KEY must be a long random value in production.")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

settings = Settings()