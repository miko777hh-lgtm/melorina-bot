import os
from dotenv import load_dotenv

load_dotenv(override=False)


def get_env(key, default=""):
    return os.environ.get(key, default)


BOT_TOKEN = get_env("BOT_TOKEN", "")
ADMIN_ID = int(get_env("ADMIN_ID", "0") or 0)
DB_PATH = get_env("DB_PATH", "zara_bot.sqlite3")
TIMEZONE = get_env("TIMEZONE", "Asia/Tehran")
BOOKS_URL = get_env("BOOKS_URL", "")

# ─── Gemini ───
GEMINI_API_KEY = get_env("GEMINI_API_KEY", "")
GEMINI_MODEL = get_env("GEMINI_MODEL", "gemini-2.5-flash")

SCHEDULER_INTERVAL = 20
BACKUP_INTERVAL = 86400
MAX_RETRIES = 3
ONETIME_DEFAULT_HOURS = 24
