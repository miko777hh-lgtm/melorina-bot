import os
from dotenv import load_dotenv

load_dotenv(override=False)


def get_env(key, default=""):
    value = os.environ.get(key, default)

    if isinstance(value, str):
        return value.strip()

    return value


BOT_TOKEN = get_env("BOT_TOKEN")
GEMINI_API_KEY = get_env("GEMINI_API_KEY")

try:
    ADMIN_ID = int(get_env("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0

GEMINI_MODEL = get_env(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
    )
