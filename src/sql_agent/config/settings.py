"""Typed application settings using Pydantic Settings.

Owner: Hassan
Status: placeholder — implement during the hackathon.

TODO:
- Define the public interface here
- Implement the logic
- Write tests in tests/unit/test_settings.py
"""

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Oracle ADB
    adb_dsn: str
    adb_user: str
    adb_password: str
    adb_wallet_location: str
    adb_wallet_password: str

    db_pool_min: int = 2
    db_pool_max: int = 10
    db_pool_timeout: int = 15
    db_pool_max_rows: int = 500

    demo_fallback_enabled: bool = False

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()