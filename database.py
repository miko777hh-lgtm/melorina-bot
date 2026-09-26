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
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                banner_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # kind: 'novel' or 'book'
        # book_type: 'pdf_full' / 'pdf_pages' / 'text'
        await db.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT DEFAULT 'novel',
                category_id INTEGER NOT NULL,
                title_fa TEXT NOT NULL,
                title_en TEXT,
                author TEXT,
                translator TEXT,
                description TEXT,
                cover TEXT,
                book_type TEXT DEFAULT 'pdf_full',
                is_paid INTEGER DEFAULT 0,
                price TEXT,
                banner_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS book_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                page_number INTEGER NOT NULL,
                content TEXT,
                file_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS book_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                file_id TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # ─── اطلاعات هر کتاب (متن، عکس، فوروارد، نقل قول...) ───
        await db.execute("""
            CREATE TABLE IF NOT EXISTS book_infos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                message_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                rating INTEGER NOT NULL,
                message TEXT,
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
            CREATE TABLE IF NOT EXISTS instant_banner (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                message_json TEXT
            )
        """)
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
        cur = await db.execute("INSERT INTO categories (name, description, banner_json) VALUES (?, ?, ?)", (name, description, banner_json))
        await db.commit()
        return cur.lastrowid


async def get_all_categories():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, name, description, banner_json FROM categories ORDER BY id ASC") as cur:
            return await cur.fetchall()


async def delete_category(cat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        await db.commit()


# ═══════════ کتاب‌ها / رمان‌ها ═══════════
async def add_book(kind, category_id, title_fa, title_en, author, translator, description, cover, book_type, is_paid, price, banner_json):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO books 
               (kind, category_id, title_fa, title_en, author, translator, description, cover, book_type, is_paid, price, banner_json) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (kind, category_id, title_fa, title_en, author, translator, description, cover, book_type, is_paid, price, banner_json)
        )
        await db.commit()
        return cur.lastrowid


async def get_all_books(kind=None):
    async with aiosqlite.connect(DB_PATH) as db:
        if kind:
            async with db.execute("SELECT id, category_id, title_fa, title_en, book_type, is_paid, price FROM books WHERE kind = ? ORDER BY id DESC", (kind,)) as cur:
                return await cur.fetchall()
        else:
            async with db.execute("SELECT id, category_id, title_fa, title_en, book_type, is_paid, price FROM books ORDER BY id DESC") as cur:
                return await cur.fetchall()


async def get_books_by_category(cat_id, kind):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, title_fa, title_en, book_type, is_paid, price FROM books WHERE category_id = ? AND kind = ? ORDER BY id ASC", (cat_id, kind)) as cur:
            return await cur.fetchall()


async def get_books_by_kind_type(kind, book_type):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, title_fa, title_en, book_type, is_paid, price FROM books WHERE kind = ? AND book_type = ? ORDER BY id ASC", (kind, book_type)) as cur:
            return await cur.fetchall()


async def get_book(book_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT id, kind, category_id, title_fa, title_en, author, translator, description, cover, 
                      book_type, is_paid, price, banner_json 
               FROM books WHERE id = ?""",
            (book_id,)
        ) as cur:
            return await cur.fetchone()


async def search_books(query):
    """جستجو تو کتاب‌ها (فقط kind=book)"""
    async with aiosqlite.connect(DB_PATH) as db:
        q = f"%{query}%"
        async with db.execute(
            """SELECT id, title_fa, title_en, book_type, is_paid 
               FROM books 
               WHERE kind = 'book' AND (title_fa LIKE ? OR title_en LIKE ? OR author LIKE ? OR description LIKE ?)
               ORDER BY id DESC LIMIT 20""",
            (q, q, q, q)
        ) as cur:
            return await cur.fetchall()


async def delete_book(book_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM books WHERE id = ?", (book_id,))
        await db.execute("DELETE FROM book_pages WHERE book_id = ?", (book_id,))
        await db.execute("DELETE FROM book_files WHERE book_id = ?", (book_id,))
        await db.execute("DELETE FROM book_infos WHERE book_id = ?", (book_id,))
        await db.commit()


# ═══════════ صفحات ═══════════
async def add_page(book_id, page_number, content=None, file_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO book_pages (book_id, page_number, content, file_id) VALUES (?, ?, ?, ?)",
            (book_id, page_number, content, file_id)
        )
        await db.commit()
        return cur.lastrowid


async def get_pages(book_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, page_number, content, file_id FROM book_pages WHERE book_id = ? ORDER BY page_number ASC", (book_id,)) as cur:
            return await cur.fetchall()


async def get_page(book_id, page_number):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, content, file_id FROM book_pages WHERE book_id = ? AND page_number = ?", (book_id, page_number)) as cur:
            return await cur.fetchone()


# ═══════════ فایل‌ها ═══════════
async def add_book_file(book_id, label, file_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO book_files (book_id, label, file_id) VALUES (?, ?, ?)", (book_id, label, file_id))
        await db.commit()
        return cur.lastrowid


async def get_book_files(book_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, label, file_id FROM book_files WHERE book_id = ? ORDER BY id ASC", (book_id,)) as cur:
            return await cur.fetchall()


# ═══════════ اطلاعات کتاب ═══════════
async def add_book_info(book_id, message_json):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO book_infos (book_id, message_json) VALUES (?, ?)", (book_id, message_json))
        await db.commit()
        return cur.lastrowid


async def get_book_infos(book_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, message_json FROM book_infos WHERE book_id = ? ORDER BY id ASC", (book_id,)) as cur:
            return await cur.fetchall()


# ═══════════ امتیازها ═══════════
async def add_rating(user_id, username, first_name, rating, message=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO ratings (user_id, username, first_name, rating, message) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, first_name, rating, message)
        )
        await db.commit()


async def has_rated(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM ratings WHERE user_id = ?", (user_id,)) as cur:
            return (await cur.fetchone())[0] > 0


async def get_all_ratings():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, user_id, first_name, rating, message, created_at FROM ratings ORDER BY id DESC") as cur:
            return await cur.fetchall()


async def get_rating_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT AVG(rating), COUNT(*) FROM ratings") as cur:
            row = await cur.fetchone()
            avg = row[0] if row[0] else 0
            count = row[1] if row[1] else 0
            return round(avg, 2), count


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


# ═══════════ بنر ═══════════
async def set_instant_banner(message_json):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO instant_banner (id, message_json) VALUES (1, ?)", (message_json,))
        await db.commit()


async def get_instant_banner():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT message_json FROM instant_banner WHERE id = 1") as cur:
            row = await cur.fetchone()
            return row[0] if row else None


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


# ═══════════ پشتیبانی ═══════════
async def add_support_msg(user_id, username, first_name, text):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO support_msgs (user_id, username, first_name, text) VALUES (?, ?, ?, ?)", (user_id, username, first_name, text))
        await db.commit()
        return cur.lastrowid


async def get_all_support_msgs(limit=50):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, user_id, first_name, text, seen, created_at FROM support_msgs ORDER BY id DESC LIMIT ?", (limit,)) as cur:
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
