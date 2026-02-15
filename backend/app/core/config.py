from typing import List, Union
from pydantic import AnyHttpUrl, validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Blind Trade Engine"
    API_V1_STR: str = "/api/v1"
    
    # -----------------------------------------------------------------------
    # SECURITY & AUTH
    # -----------------------------------------------------------------------
    SECRET_KEY: str = "CHANGE_THIS_IN_PRODUCTION_TO_A_STRONG_SECRET"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    
    # -----------------------------------------------------------------------
    # CORS
    # -----------------------------------------------------------------------
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = ["http://localhost:5173", "http://localhost:3000"]

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # -----------------------------------------------------------------------
    # DATABASE (POSTGRESQL)
    # -----------------------------------------------------------------------
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "blind_trade_db"
    SQLALCHEMY_DATABASE_URI: str | None = None

    @validator("SQLALCHEMY_DATABASE_URI", pre=True)
    def assemble_db_connection(cls, v: str | None, values: dict[str, any]) -> any:
        if isinstance(v, str):
            return v
        
        # FIX: Force absolute path to avoid CWD ambiguity (Root vs Backend job mismatch)
        import os
        # app/core/config.py -> app/core -> app -> backend (ROOT of backend)
        current_file = os.path.abspath(__file__)
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
        db_path = os.path.join(backend_dir, "blind_trade.db")
        
        return f"sqlite+aiosqlite:///{db_path}"

    # -----------------------------------------------------------------------
    # MARKET DATA API
    # -----------------------------------------------------------------------
    MARKET_DATA_API_KEY: str | None = None
    MARKET_DATA_PROVIDER: str = "twelvedata" # default

    # -----------------------------------------------------------------------
    # REDIS (CACHE)
    # -----------------------------------------------------------------------
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()
