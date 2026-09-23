import os
from dotenv import load_dotenv

load_dotenv(override=False)


def get_env(key, default=""):
    return os.environ.get(key, default)


BOT_TOKEN = get_env("BOT_TOKEN", "")
ADMIN_ID = int(get_env("ADMIN_ID", "0") or 0)
DB_PATH = get_env("DB_PATH", "zara_bot.sqlite3")
TIMEZONE = get_env("TIMEZONE", "Asia/Tehran")

SCHEDULER_INTERVAL = 20
BACKUP_INTERVAL = 86400
