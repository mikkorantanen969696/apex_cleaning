from __future__ import annotations

from typing import Dict, List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    admin_telegram_ids: str = ""

    supergroup_chat_id: int | None = None
    city_threads: str = ""

    sqlite_path: str = "./apex_cleaning.db"
    database_url: str = ""

    business_tz: str = "Asia/Novosibirsk"

    company_name: str = ""
    company_inn: str = ""
    company_bank: str = ""
    company_account: str = ""
    company_bik: str = ""
    company_corr_account: str = ""
    payment_purpose_template: str = "Оплата услуг по заявке {order_public_id}"

    send_admin_notifications: int = 1

    @staticmethod
    def _strip_env_assignment(value: str, key: str) -> str:
        value = value.strip().strip('"').strip("'").strip()
        prefix = f"{key}="
        if value.upper().startswith(prefix.upper()):
            return value.split("=", 1)[1].strip().strip('"').strip("'").strip()
        return value

    @field_validator("bot_token", mode="before")
    @classmethod
    def _normalize_bot_token(cls, v):
        if isinstance(v, str):
            return cls._strip_env_assignment(v, "BOT_TOKEN")
        return v

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, v):
        if isinstance(v, str):
            return cls._strip_env_assignment(v, "DATABASE_URL")
        return v

    @field_validator("sqlite_path", mode="before")
    @classmethod
    def _normalize_sqlite_path(cls, v):
        if isinstance(v, str):
            return cls._strip_env_assignment(v, "SQLITE_PATH")
        return v

    def admin_ids(self) -> List[int]:
        if not self.admin_telegram_ids.strip():
            return []
        result: List[int] = []
        for part in self.admin_telegram_ids.split(","):
            part = part.strip()
            if not part:
                continue
            result.append(int(part))
        return result

    def city_thread_map(self) -> Dict[str, int]:
        mapping: Dict[str, int] = {}
        raw = self.city_threads.strip()
        if not raw:
            return mapping
        for pair in raw.split(";"):
            pair = pair.strip()
            if not pair:
                continue
            if "=" not in pair:
                continue
            name, thread_id = pair.split("=", 1)
            name = name.strip()
            thread_id = thread_id.strip()
            if not name or not thread_id:
                continue
            mapping[name] = int(thread_id)
        return mapping


settings = Settings()
