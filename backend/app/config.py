from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "xlsx-mapper"
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 60 * 24
    database_url: str = "postgresql+psycopg2://xlsx_mapper:xlsx_mapper@db:5432/xlsx_mapper"
    storage_dir: str = "/data"
    session_ttl_hours: int = 24

    model_config = SettingsConfigDict(env_file=".env", env_prefix="XLSX_MAPPER_")


settings = Settings()
