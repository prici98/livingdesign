# =============================================================================
#  La configuration du projet, lue et vérifiée par Pydantic
# =============================================================================

from functools import lru_cache            
from pathlib import Path

from pydantic import SecretStr               
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_env_file() -> Path | None:
    """Renvoie le chemin du .env à utiliser, ou None si aucun n'existe. """
    for folder in [Path.cwd(), *Path.cwd().parents]:    # le dossier courant, puis chaque parent
        candidate = folder / "infra" / ".env"
        if candidate.is_file():
            return candidate
    return None


class Settings(BaseSettings):
    """La configuration du projet, lue et vérifiée par Pydantic."""
    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",                      
    )

    # --- PostgreSQL ---
    postgres_host: str = "localhost"        
    postgres_port: int = 5432
    postgres_db: str = "livingdesign"
    
    orders_db_password: SecretStr
    inventory_db_password: SecretStr
    payments_db_password: SecretStr

    # --- MongoDB ---
    mongo_host: str = "localhost"
    mongo_port: int = 27017
    mongo_db: str = "livingdesign"
    catalog_db_password: SecretStr

    # --- Données générées ---
    seed_customers: int = 3000
    seed_orders: int = 20000
    seed_months: int = 6


@lru_cache                                 
def get_settings() -> Settings:
    return Settings()
