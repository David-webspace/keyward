from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_ignore_empty=True)

    database_url: str
    jwt_secret: str  # 不給預設值：沒設定就啟動失敗，避免用到可猜測的固定金鑰
    # demo = 從 HR 名冊選人登入（只限本機示範）；entra = Entra ID SSO（尚未實作）。刻意不給預設值
    auth_mode: str
    jwt_ttl_hours: int = 12
    cookie_secure: bool = False
    data_dir: Path = ROOT / "data"
    web_base_url: str = "http://localhost:3500"

    # 通知信：示範環境寄到 Mailpit；收件網域白名單在程式層面擋掉真實網域
    smtp_host: str | None = None
    smtp_port: int = 1027
    mail_from: str = "keyward@arcwell.example"
    allowed_recipient_suffix: str = ".example"


@lru_cache
def get_settings() -> Settings:
    return Settings()
