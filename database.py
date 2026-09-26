import aiosqlite
import json
import os

DB_PATH = os.environ.get("DB_PATH", "zara_bot.sqlite3")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # ─── کاربران ───
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # ─── ژانرها ───
        await db.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                banner_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # ─── کتاب‌ها / رمان‌ها ───
        await db.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                title_fa TEXT NOT NULL,
                title_en TEXT,
                author TEXT,
                translator TEXT,
                description TEXT,
                cover TEXT,
                book_type TEXT DEFAULT 'pdf',
                is_paid INTEGER DEFAULT 0,
                price TEXT,
                preview_pages INTEGER DEFAULT 0,
                banner_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # ─── صفحات رمان متنی ───
        await db.execute("""
            CREATE TABLE IF NOT EXISTS book_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                page_number INTEGER NOT NULL,
                content TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # ─── فایل‌های کتاب (PDF، صوتی و...) ───
        await db.execute("""
            CREATE TABLE IF NOT EXISTS book_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                file_id TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # ─── کانال‌ها ───
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT UNIQUE NOT NULL,
                title TEXT,
                invite_link TEXT
            )
        """)
        # ─── بنر فوری ───
        await db.execute("""
            CREATE TABLE IF NOT EXISTS instant_banner (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                message_json TEXT
            )
        """)
        # ─── بنر زمان‌بندی ───
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_banners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_json TEXT NOT NULL,
                run_at TEXT NOT NULL,
                sent INTEGER DEFAULT 0,
                retries INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # ─── لینک یکبار مصرف ───
        await db.execute("""
            CREATE TABLE IF NOT EXISTS onetime_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                book_id INTEGER NOT NULL,
                used INTEGER DEFAULT 0,
                expires_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # ─── پشتیبانی ───
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
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()


# ═══════════ کاربران ═══════════
async def add_user(user_id, username, first_name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)", (user_id, username, first_name))
        await db.commit()


async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            return [r[0] for r in await cur.fetchall()]


async def get_users_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            return (await cur.fetchone())[0]


# ═══════════ ژانرها ═══════════
async def add_category(name, description, banner_json=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO categories (name, description, banner_json) VALUES (?, ?, ?)",
            (name, description, banner_json)
        )
        await db.commit()
        return cur.lastrowid


async def get_all_categories():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, name, description, banner_json FROM categories ORDER BY id ASC") as cur:
            return await cur.fetchall()


async def get_category(cat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, name, description, banner_json FROM categories WHERE id = ?", (cat_id,)) as cur:
            return await cur.fetchone()


async def delete_category(cat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        await db.commit()


# ═══════════ کتاب‌ها ═══════════
async def add_book(category_id, title_fa, title_en, author, translator, description, cover, book_type, is_paid, price, preview_pages, banner_json):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO books 
               (category_id, title_fa, title_en, author, translator, description, cover, book_type, is_paid, price, preview_pages, banner_json) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (category_id, title_fa, title_en, author, translator, description, cover, book_type, is_paid, price, preview_pages, banner_json)
        )
        await db.commit()
        return cur.lastrowid


async def get_all_books():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, category_id, title_fa, title_en, book_type, is_paid, price FROM books ORDER BY id DESC"
        ) as cur:
            return await cur.fetchall()


async def get_books_by_category(cat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, title_fa, title_en, book_type, is_paid, price FROM books WHERE category_id = ? ORDER BY id ASC",
            (cat_id,)
        ) as cur:
            return await cur.fetchall()


async def get_book(book_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT id, category_id, title_fa, title_en, author, translator, description, cover, 
                      book_type, is_paid, price, preview_pages, banner_json 
               FROM books WHERE id = ?""",
            (book_id,)
        ) as cur:
            return await cur.fetchone()


async def update_book_field(book_id, field, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE books SET {field} = ? WHERE id = ?", (value, book_id))
        await db.commit()


async def delete_book(book_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM books WHERE id = ?", (book_id,))
        await db.execute("DELETE FROM book_pages WHERE book_id = ?", (book_id,))
        await db.execute("DELETE FROM book_files WHERE book_id = ?", (book_id,))
        await db.commit()


# ═══════════ صفحات (رمان متنی) ═══════════
async def add_page(book_id, page_number, content):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO book_pages (book_id, page_number, content) VALUES (?, ?, ?)",
            (book_id, page_number, content)
        )
        await db.commit()
        return cur.lastrowid


async def get_pages(book_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, page_number, content FROM book_pages WHERE book_id = ? ORDER BY page_number ASC",
            (book_id,)
        ) as cur:
            return await cur.fetchall()


async def get_page(book_id, page_number):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, content FROM book_pages WHERE book_id = ? AND page_number = ?",
            (book_id, page_number)
        ) as cur:
            return await cur.fetchone()


async def update_page(page_id, content):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE book_pages SET content = ? WHERE id = ?", (content, page_id))
        await db.commit()


async def delete_page(page_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM book_pages WHERE id = ?", (page_id,))
        await db.commit()


# ═══════════ فایل‌های کتاب ═══════════
async def add_book_file(book_id, label, file_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO book_files (book_id, label, file_id) VALUES (?, ?, ?)",
            (book_id, label, file_id)
        )
        await db.commit()
        return cur.lastrowid


async def get_book_files(book_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, label, file_id FROM book_files WHERE book_id = ? ORDER BY id ASC",
            (book_id,)
        ) as cur:
            return await cur.fetchall()


async def delete_book_file(file_id_db):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM book_files WHERE id = ?", (file_id_db,))
        await db.commit()


# ═══════════ کانال‌ها ═══════════
async def add_channel(chat_id, title, invite_link):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO channels (chat_id, title, invite_link) VALUES (?, ?, ?)", (chat_id, title, invite_link))
        await db.commit()


async def get_all_channels():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, chat_id, title, invite_link FROM channels") as cur:
            return await cur.fetchall()


async def delete_channel(channel_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
        await db.commit()


# ═══════════ بنر فوری ═══════════
async def set_instant_banner(message_json):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO instant_banner (id, message_json) VALUES (1, ?)", (message_json,))
        await db.commit()


async def get_instant_banner():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT message_json FROM instant_banner WHERE id = 1") as cur:
            row = await cur.fetchone()
            return row[0] if row else None


# ═══════════ بنر زمان‌بندی ═══════════
async def add_scheduled_banner(message_json, run_at):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO scheduled_banners (message_json, run_at) VALUES (?, ?)", (message_json, run_at))
        await db.commit()
        return cur.lastrowid


async def get_pending_banners():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, message_json, run_at FROM scheduled_banners WHERE sent = 0 AND retries < 3") as cur:
            return await cur.fetchall()


async def get_all_scheduled_banners():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, message_json, run_at, sent FROM scheduled_banners ORDER BY run_at ASC") as cur:
            return await cur.fetchall()


async def mark_banner_sent(bid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE scheduled_banners SET sent = 1 WHERE id = ?", (bid,))
        await db.commit()


async def increment_banner_retry(bid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE scheduled_banners SET retries = retries + 1 WHERE id = ?", (bid,))
        await db.commit()


async def delete_scheduled_banner(bid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM scheduled_banners WHERE id = ?", (bid,))
        await db.commit()


# ═══════════ لینک یکبار مصرف ═══════════
async def add_onetime_link(code, book_id, expires_at):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO onetime_links (code, book_id, expires_at) VALUES (?, ?, ?)", (code, book_id, expires_at))
        await db.commit()
        return cur.lastrowid


async def get_onetime_link(code):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, book_id, used, expires_at FROM onetime_links WHERE code = ?", (code,)) as cur:
            return await cur.fetchone()


async def mark_onetime_used(code):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE onetime_links SET used = 1 WHERE code = ?", (code,))
        await db.commit()


async def get_all_onetime_links():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, code, book_id, used, expires_at, created_at FROM onetime_links ORDER BY id DESC") as cur:
            return await cur.fetchall()


async def delete_onetime_link(link_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM onetime_links WHERE id = ?", (link_id,))
        await db.commit()


# ═══════════ پشتیبانی ═══════════
async def add_support_msg(user_id, username, first_name, text):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO support_msgs (user_id, username, first_name, text) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, text)
        )
        await db.commit()
        return cur.lastrowid


async def get_all_support_msgs(limit=50):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, user_id, first_name, text, seen, created_at FROM support_msgs ORDER BY id DESC LIMIT ?",
            (limit,)
        ) as cur:
            return await cur.fetchall()


async def get_support_msg(msg_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, user_id, first_name, text FROM support_msgs WHERE id = ?", (msg_id,)) as cur:
            return await cur.fetchone()


async def mark_support_seen(msg_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE support_msgs SET seen = 1 WHERE id = ?", (msg_id,))
        await db.commit()


async def get_support_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM support_msgs") as cur:
            return (await cur.fetchone())[0]


# ═══════════ FSM ═══════════
async def set_fsm(user_id, state, data=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO fsm_state (user_id, state, data) VALUES (?, ?, ?)", (user_id, state, json.dumps(data or {}, ensure_ascii=False)))
        await db.commit()


async def get_fsm(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT state, data FROM fsm_state WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return row[0], json.loads(row[1])
            return None, {}


async def clear_fsm(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM fsm_state WHERE user_id = ?", (user_id,))
        await db.commit()
