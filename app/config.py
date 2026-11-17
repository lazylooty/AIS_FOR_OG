from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg2://realtor_user:realtor_secret_password@localhost:5432/realtor_db"
    )
    storage_dir: Path = Path("/app/storage")
    agency_name: str = "ИП Голубина Ольга Геннадьевна"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def templates_dir(self) -> Path:
        path = self.storage_dir / "templates"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def contracts_dir(self) -> Path:
        path = self.storage_dir / "contracts"
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
