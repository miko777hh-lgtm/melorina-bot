import aiosqlite
import json
import os

DB_PATH = os.environ.get("DB_PATH", "zara_bot.sqlite3")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                caption TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT UNIQUE NOT NULL,
                title TEXT,
                invite_link TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS banner (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                file_id TEXT,
                file_type TEXT,
                caption TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS onetime_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                file_id_db INTEGER NOT NULL,
                used INTEGER DEFAULT 0,
                expires_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS support_msgs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                text TEXT,
                seen INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fsm_state (
                user_id INTEGER PRIMARY KEY,
                state TEXT,
                data TEXT DEFAULT '{}'
            )
        """)
        await db.commit()


# ═══════════ تنظیمات ═══════════
async def get_setting(key, default=None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else default


async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value))
        )
        await db.commit()


# ═══════════ کاربران ═══════════
async def add_user(user_id, username, first_name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
            (user_id, username, first_name)
        )
        await db.commit()


async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            return [r[0] for r in await cur.fetchall()]


async def get_users_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            return (await cur.fetchone())[0]


# ═══════════ فایل‌ها ═══════════
async def add_file(file_id, file_type, caption):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO files (file_id, file_type, caption) VALUES (?, ?, ?)",
            (file_id, file_type, caption)
        )
        await db.commit()
        return cur.lastrowid


async def get_all_files():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, file_id, file_type, caption FROM files ORDER BY id DESC"
        ) as cur:
            return await cur.fetchall()


async def get_file(file_id_db):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT file_id, file_type, caption FROM files WHERE id = ?",
            (file_id_db,)
        ) as cur:
            return await cur.fetchone()


async def update_caption(file_id_db, new_caption):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE files SET caption = ? WHERE id = ?",
            (new_caption, file_id_db)
        )
        await db.commit()


async def delete_file(file_id_db):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM files WHERE id = ?", (file_id_db,))
        await db.commit()


# ═══════════ کانال‌ها ═══════════
async def add_channel(chat_id, title, invite_link):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO channels (chat_id, title, invite_link) VALUES (?, ?, ?)",
            (chat_id, title, invite_link)
        )
        await db.commit()


async def get_all_channels():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, chat_id, title, invite_link FROM channels"
        ) as cur:
            return await cur.fetchall()


async def delete_channel(channel_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
        await db.commit()


# ═══════════ بنر ═══════════
async def set_banner(file_id, file_type, caption):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO banner (id, file_id, file_type, caption) VALUES (1, ?, ?, ?)",
            (file_id, file_type, caption)
        )
        await db.commit()


async def get_banner():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT file_id, file_type, caption FROM banner WHERE id = 1"
        ) as cur:
            return await cur.fetchone()


# ═══════════ لینک یکبار مصرف ═══════════
async def add_onetime_link(code, file_id_db, expires_at):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO onetime_links (code, file_id_db, expires_at) VALUES (?, ?, ?)",
            (code, file_id_db, expires_at)
        )
        await db.commit()
        return cur.lastrowid


async def get_onetime_link(code):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, file_id_db, used, expires_at FROM onetime_links WHERE code = ?",
            (code,)
        ) as cur:
            return await cur.fetchone()


async def mark_onetime_used(code):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE onetime_links SET used = 1 WHERE code = ?", (code,))
        await db.commit()


async def get_all_onetime_links():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, code, file_id_db, used, expires_at, created_at FROM onetime_links ORDER BY id DESC"
        ) as cur:
            return await cur.fetchall()


async def delete_onetime_link(link_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM onetime_links WHERE id = ?", (link_id,))
        await db.commit()


# ═══════════ پشتیبانی ═══════════
async def add_support_msg(user_id, username, first_name, text):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO support_msgs 
               (user_id, username, first_name, text) 
               VALUES (?, ?, ?, ?)""",
            (user_id, username, first_name, text)
        )
        await db.commit()
        return cur.lastrowid


async def get_all_support_msgs(limit=50):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT id, user_id, first_name, text, seen, created_at 
               FROM support_msgs ORDER BY id DESC LIMIT ?""",
            (limit,)
        ) as cur:
            return await cur.fetchall()


async def get_support_msg(msg_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, user_id, first_name, text FROM support_msgs WHERE id = ?",
            (msg_id,)
        ) as cur:
            return await cur.fetchone()


async def mark_support_seen(msg_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE support_msgs SET seen = 1 WHERE id = ?", (msg_id,))
        await db.commit()


async def delete_support_msg(msg_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM support_msgs WHERE id = ?", (msg_id,))
        await db.commit()


async def get_support_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM support_msgs") as cur:
            return (await cur.fetchone())[0]


# ═══════════ FSM ═══════════
async def set_fsm(user_id, state, data=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO fsm_state (user_id, state, data) VALUES (?, ?, ?)",
            (user_id, state, json.dumps(data or {}))
        )
        await db.commit()


async def get_fsm(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT state, data FROM fsm_state WHERE user_id = ?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return row[0], json.loads(row[1])
            return None, {}


async def clear_fsm(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM fsm_state WHERE user_id = ?", (user_id,))
        await db.commit()
