### apex_cleaning bot

**Требования**
- Python 3.11+
- Postgres (опционально; по умолчанию SQLite)

**Настройка**
1) Скопируй `.env.example` -> `.env` и заполни минимум:
- `BOT_TOKEN=...`
- `ADMIN_TELEGRAM_IDS=...` (твой Telegram user_id, можно несколько через запятую)
- `DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/cleaning_vot` (если хочешь Postgres)  
  или оставь пустым и используй SQLite (`SQLITE_PATH`)

2) Установи зависимости:
- `pip install -r requirements.txt`

**Запуск**
- `python -m app`
