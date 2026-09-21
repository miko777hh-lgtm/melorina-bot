import os
from dotenv import load_dotenv

load_dotenv(override=False)


def get_env(key, default=""):
    return os.environ.get(key, default)


BOT_TOKEN = get_env("BOT_TOKEN", "")
ADMIN_ID = int(get_env("ADMIN_ID", "0") or 0)
GEMINI_API_KEY = get_env("GEMINI_API_KEY", "")
GEMINI_MODEL = get_env("GEMINI_MODEL", "gemini-2.5-flash")
