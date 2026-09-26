import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

import database as db
from config import BOT_TOKEN, ADMIN_ID
from texts import *
from replies import get_ready_reply
from force_join import is_user_joined, send_join_prompt, check_join_callback
from admin_panel import (
    admin_reply_keyboard, user_reply_keyboard,
    is_admin, show_admin_panel
)
from banner import capture_message, send_captured, broadcast_instant_banner
from scheduler import process_scheduled_banners, process_inactive_users
from onetime_link import create_onetime_link, use_onetime_link, generate_bot_link

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
TZ = ZoneInfo("Asia/Tehran")


def parse_datetime(text):
    try:
        parts = text.strip().split()
        date_part = parts[0]
        time_part = parts[1] if len(parts) > 1 else "00:00"
        y, m, d = map(int, date_part.split("-"))
        hh, mm = map(int, time_part.split(":"))
        if y < 1500:
            from jalali import jalali_to_gregorian
            gy, gm, gd = jalali_to_gregorian(y, m, d)
            dt = datetime(gy, gm, gd, hh, mm, tzinfo=TZ)
        else:
            dt = datetime(y, m, d, hh, mm, tzinfo=TZ)
        return dt.isoformat()
    except Exception:
        return None


def pages_keyboard(book_id, total_pages):
    keyboard = []
    row = []
    for i in range(1, total_pages + 1):
        row.append(InlineKeyboardButton(str(i), callback_data=f"pg_{book_id}_{i}"))
        if len(row) == 6:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)


def kind_icon(kind, btype):
    return {"text": "📝", "pdf_full": "📄", "pdf_pages": "📑"}.get(btype, "📖")


# ═══════════ چک ری‌اکشن ═══════════
async def check_reactions(context, user_id):
    """چک میکنه کاربر به آخرین پست‌های کانال ری‌اکشن زده یا نه"""
    required = int(await db.get_setting("reaction_required", "5") or 5)
    if required <= 0:
        return True, 0, required

    posts = await db.get_recent_channel_posts(limit=required)
    if not posts:
        return True, 0, required

    # گروه‌بندی بر اساس chat_id
    by_chat = {}
    for chat_id, msg_id in posts:
        by_chat.setdefault(chat_id, []).append(msg_id)

    total_reacted = 0
    total_posts = 0

    for chat_id, msg_ids in by_chat.items():
        total_posts += len(msg_ids)
        # چک میکنه کدوم پیام‌ها رو کاربر ری‌اکشن زده
        # با استفاده از get_message_reactions یا از دیتابیس خودمون
        # اینجا فرض می‌کنیم از دیتابیس خودمون (با اسکن پیام‌ها)
        for mid in msg_ids:
            try:
                # چک ری‌اکشن‌های پیام
                # telegram API فعلاً اجازه خواندن ری‌اکشن‌های همه کاربرا رو نمیده
                # پس باید از دیتابیس خودمون استفاده کنیم
                pass
            except Exception:
                pass

    return total_reacted >= required, total_reacted, required


# ═══════════ استارت ═══════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.add_user(user.id, user.username, user.first_name)
    args = context.args

    if args and args[0].startswith("otl_"):
        code = args[0][4:]
        result = await use_onetime_link(code)
        if not result["ok"]:
            reason = result.get("reason")
            if reason == "used":
                await update.message.reply_text(OTL_USED)
            elif reason == "expired":
                await update.message.reply_text(OTL_EXPIRED)
            else:
                await update.message.reply_text(OTL_INVALID)
            return
        if not await is_user_joined(context, user.id):
            await send_join_prompt(update, context)
            return
        await update.message.reply_text(OTL_WELCOME)
        await send_book_to_user(context, user.id, result["book_id"])
        return

    if is_admin(user.id):
        await show_admin_panel(update, context)
        return

    if not await is_user_joined(context, user.id):
        await send_join_prompt(update, context)
        return

    await update.message.reply_text(WELCOME_AFTER_JOIN, reply_markup=await build_user_keyboard())


# ═══════════ کیبورد کاربر با دکمه‌های سفارشی ═══════════
async def build_user_keyboard():
    from telegram import ReplyKeyboardMarkup
    buttons = [
        ["📚 کتاب‌ها", "📖 رمان‌ها"],
        ["🌐 فیلترشکن", "🔍 جستجو"],
        ["⭐ امتیاز به ربات", "📩 تماس با پشتیبانی"],
    ]
    # دکمه‌های سفارشی
    custom = await db.get_all_custom_buttons()
    for cb in custom:
        bid, name, mjson = cb
        buttons.append([f"🎯 {name}"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


# ═══════════ ارسال محتوا ═══════════
async def send_book_to_user(context, chat_id, book_id):
    book = await db.get_book(book_id)
    if not book:
        await context.bot.send_message(chat_id, BOOK_NOT_FOUND)
        return
    b_id, kind, cat_id, title_fa, title_en, author, translator, desc, cover, btype, is_paid, price, banner = book

    header = f"📖 {title_fa}\n"
    if title_en:
        header += f"📕 {title_en}\n"
    if author:
        header += f"✍️ {author}\n"
    if translator:
        header += f"🖋 مترجم: {translator}\n"
    header += "\n"

    infos = await db.get_book_infos(b_id)
    for info in infos:
        try:
            await send_captured(context, chat_id, info[1])
        except Exception:
            pass

    if btype == "text" or btype == "pdf_pages":
        pages = await db.get_pages(b_id)
        if not pages:
            await context.bot.send_message(chat_id, "📭 صفحه‌ای نیست.")
            return
        await context.bot.send_message(chat_id, header + "صفحه موردنظر:", reply_markup=pages_keyboard(b_id, len(pages)))
    elif btype == "pdf_full":
        files = await db.get_book_files(b_id)
        if not files:
            await context.bot.send_message(chat_id, "📭 فایلی نیست.")
            return
        await context.bot.send_message(chat_id, header)
        for f in files:
            try:
                await context.bot.send_document(chat_id, f[2], caption=f[1])
            except Exception:
                pass

    if banner:
        await send_captured(context, chat_id, banner)


# ═══════════ کال‌بک ═══════════
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "check_join":
        await check_join_callback(update, context)
        return

    # ═══════════ VPN Links ═══════════
    if data.startswith("vpn_"):
        vid = int(data.split("_")[1])
        links = await db.get_all_vpn_links()
        found = None
        for l in links:
            if l[0] == vid:
                found = l
                break
        if found:
            try:
                await send_captured(context, user_id, found[2])
            except Exception:
                await query.edit_message_text("❌ خطا در ارسال.")
        else:
            await query.edit_message_text("❌ پیدا نشد.")
        return

    # ═══════════ Custom Buttons ═══════════
    if data.startswith("custom_"):
        bid = int(data.split("_")[1])
        custom = await db.get_all_custom_buttons()
        found = None
        for c in custom:
            if c[0] == bid:
                found = c
                break
        if found:
            try:
                await send_captured(context, user_id, found[2])
            except Exception:
                await query.edit_message_text("❌ خطا در ارسال.")
        return

    # ═══════════ ژانرها ═══════════
    if data.startswith("cat_"):
        parts = data.split("_")
        cid = int(parts[1])
        kind = parts[2]
        books = await db.get_books_by_category(cid, kind)
        if not books:
            await query.edit_message_text("📭 تو این ژانر چیزی نیست.")
            return
        kb = []
        for b in books:
            bid, tfa, ten, btype, is_paid, price = b
            prefix = "💳" if is_paid else "🆓"
            icon = kind_icon(kind, btype)
            kb.append([InlineKeyboardButton(f"{prefix}{icon} {tfa}", callback_data=f"book_{bid}")])
        back = "user_cats_novel" if kind == "novel" else "user_cats_book"
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back)])
        await query.edit_message_text("📖 لیست:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data == "user_cats_novel":
        cats = await db.get_all_categories()
        if not cats:
            await query.edit_message_text("📭 ژانری نیست.")
            return
        kb = [[InlineKeyboardButton(f"📁 {c[1]}", callback_data=f"cat_{c[0]}_novel")] for c in cats]
        await query.edit_message_text("📚 ژانرها:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data == "user_cats_book":
        cats = await db.get_all_categories()
        if not cats:
            await query.edit_message_text("📭 ژانری نیست.")
            return
        kb = [[InlineKeyboardButton(f"📁 {c[1]}", callback_data=f"cat_{c[0]}_book")] for c in cats]
        await query.edit_message_text("📚 ژانرها:", reply_markup=InlineKeyboardMarkup(kb))
        return

    # ═══════════ انتخاب رمان/کتاب ═══════════
    if data.startswith("book_"):
        bid = int(data.split("_")[1])
        book = await db.get_book(bid)
        if not book:
            await query.edit_message_text(BOOK_NOT_FOUND)
            return
        b_id, kind, cat_id, title_fa, title_en, author, translator, desc, cover, btype, is_paid, price, banner = book

        info = f"📖 {title_fa}\n"
        if title_en:
            info += f"📕 {title_en}\n"
        if author:
            info += f"✍️ {author}\n"
        if translator:
            info += f"🖋 {translator}\n"
        if desc:
            info += f"\n📝 {desc}\n"

        if is_paid == 1:
            info += f"\n💳 قیمت: {price or 'تماس با ادمین'}\n\nبرای خرید:\n👤 @Yuriii79"
            kb = [[InlineKeyboardButton("📩 خرید", url="https://t.me/Yuriii79")]]
            await query.edit_message_text(info, reply_markup=InlineKeyboardMarkup(kb))
            return

        # چک ری‌اکشن (فقط برای لینک یکبار مصرف)
        # اینجا چک نمی‌کنیم، تو start چک میشه

        if btype == "text" or btype == "pdf_pages":
            pages = await db.get_pages(b_id)
            if not pages:
                await query.edit_message_text("📭 صفحه‌ای نیست.")
                return
            await query.edit_message_text(info + "\nصفحه موردنظر:", reply_markup=pages_keyboard(b_id, len(pages)))
        elif btype == "pdf_full":
            files = await db.get_book_files(b_id)
            if not files:
                await query.edit_message_text("📭 فایلی نیست.")
                return
            await query.edit_message_text(info)
            for f in files:
                try:
                    await context.bot.send_document(user_id, f[2], caption=f[1])
                except Exception:
                    pass

        infos = await db.get_book_infos(b_id)
        for inf in infos:
            try:
                await send_captured(context, user_id, inf[1])
            except Exception:
                pass

        if banner:
            await send_captured(context, user_id, banner)
        return

    # ═══════════ ارسال صفحه ═══════════
    if data.startswith("pg_"):
        parts = data.split("_")
        bid = int(parts[1])
        page_num = int(parts[2])
        page = await db.get_page(bid, page_num)
        if not page:
            await query.answer("صفحه پیدا نشد.", show_alert=True)
            return
        page_id, content, file_id = page
        if content:
            await context.bot.send_message(user_id, f"📄 صفحه {page_num}\n\n{content}")
        elif file_id:
            try:
                await context.bot.send_document(user_id, file_id, caption=f"صفحه {page_num}")
            except Exception:
                pass
        return

    # ═══════════ امتیاز ═══════════
    if data.startswith("rate_"):
        rating = int(data.split("_")[1])
        await db.add_rating(user_id, query.from_user.username, query.from_user.first_name, rating, None)
        await query.edit_message_text(f"⭐ امتیازت ثبت شد: {'⭐' * rating}\n\nاگه حرفی داری، بنویس 👇")
        await db.set_fsm(user_id, "awaiting_rating_msg")
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"⭐ امتیاز جدید\n\n👤 {query.from_user.first_name}\n🆔 `{query.from_user.id}`\n📛 @{query.from_user.username or 'ندارد'}\n⭐ {rating} از ۵",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        return

    # ═══════════ جستجو ═══════════
    if data == "search_start":
        await db.set_fsm(user_id, "awaiting_search")
        await query.edit_message_text(SEARCH_PROMPT)
        return

    # ═══════════ فقط ادمین ═══════════
    if not is_admin(user_id):
        return

    # ژانرها
    if data == "newcat":
        await db.set_fsm(user_id, "awaiting_cat_name")
        await query.edit_message_text("📝 اسم ژانر:")
        return
    if data == "admin_list_cats":
        cats = await db.get_all_categories()
        if not cats:
            await query.edit_message_text("📭 ژانری نیست.")
            return
        text = "📁 ژانرها:\n\n"
        for c in cats:
            text += f"#{c[0]} | {c[1]}\n"
        await query.edit_message_text(text)
        return
    if data == "admin_del_cat":
        cats = await db.get_all_categories()
        if not cats:
            await query.edit_message_text("📭 ژانری نیست.")
            return
        kb = [[InlineKeyboardButton(f"🗑 {c[1]}", callback_data=f"delcat_{c[0]}")] for c in cats]
        await query.edit_message_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
        return
    if data.startswith("delcat_"):
        cid = int(data.split("_")[1])
        await db.delete_category(cid)
        await query.edit_message_text("✅ حذف شد.")
        return

    # رمان‌ها / کتاب‌ها منو
    if data == "admin_novel_menu":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 PDF کلی", callback_data="novel_menu_pdf_full")],
            [InlineKeyboardButton("📑 PDF صفحه‌ای", callback_data="novel_menu_pdf_pages")],
            [InlineKeyboardButton("📝 نوشته‌ای", callback_data="novel_menu_text")],
        ])
        await query.edit_message_text("📖 رمان‌ها:", reply_markup=kb)
        return
    if data == "admin_book_menu":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 PDF کلی", callback_data="book_menu_pdf_full")],
            [InlineKeyboardButton("📑 PDF صفحه‌ای", callback_data="book_menu_pdf_pages")],
            [InlineKeyboardButton("📝 نوشته‌ای", callback_data="book_menu_text")],
        ])
        await query.edit_message_text("📚 کتاب‌ها:", reply_markup=kb)
        return

    if data.startswith("novel_menu_"):
        btype = data.replace("novel_menu_", "")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ افزودن", callback_data=f"newbook_novel_{btype}")],
            [InlineKeyboardButton("📋 لیست", callback_data=f"list_{btype}_novel")],
            [InlineKeyboardButton("🗑 حذف", callback_data=f"delbooks_{btype}_novel")],
        ])
        await query.edit_message_text("📖 مدیریت:", reply_markup=kb)
        return

    if data.startswith("book_menu_"):
        btype = data.replace("book_menu_", "")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ افزودن", callback_data=f"newbook_book_{btype}")],
            [InlineKeyboardButton("📋 لیست", callback_data=f"list_{btype}_book")],
            [InlineKeyboardButton("🗑 حذف", callback_data=f"delbooks_{btype}_book")],
        ])
        await query.edit_message_text("📚 مدیریت:", reply_markup=kb)
        return

    if data.startswith("newbook_"):
        parts = data.split("_")
        kind = parts[1]
        btype = "_".join(parts[2:])
        cats = await db.get_all_categories()
        if not cats:
            await query.edit_message_text("❌ اول ژانر بساز.")
            return
        kb = [[InlineKeyboardButton(c[1], callback_data=f"selcat_{kind}_{btype}_{c[0]}")] for c in cats]
        await query.edit_message_text("📁 ژانر:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("selcat_"):
        parts = data.split("_")
        kind = parts[1]
        btype = parts[2]
        cid = int(parts[3])
        await db.set_fsm(user_id, "awaiting_book_name_fa", {"category_id": cid, "kind": kind, "book_type": btype})
        await query.edit_message_text("📖 اسم فارسی:")
        return

    if data.startswith("list_"):
        parts = data.split("_")
        btype = "_".join(parts[1:-1])
        kind = parts[-1]
        books = await db.get_books_by_kind_type(kind, btype)
        if not books:
            await query.edit_message_text("📭 چیزی نیست.")
            return
        text = "📋 لیست:\n\n"
        for b in books:
            t = "💳" if b[4] else "🆓"
            text += f"#{b[0]} | {t} {b[1]}\n"
        await query.edit_message_text(text)
        return

    if data.startswith("delbooks_"):
        parts = data.split("_")
        btype = "_".join(parts[1:-1])
        kind = parts[-1]
        books = await db.get_books_by_kind_type(kind, btype)
        if not books:
            await query.edit_message_text("📭 چیزی نیست.")
            return
        kb = [[InlineKeyboardButton(f"🗑 {b[1]}", callback_data=f"delbook_{b[0]}")] for b in books]
        await query.edit_message_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("delbook_"):
        bid = int(data.split("_")[1])
        await db.delete_book(bid)
        await query.edit_message_text("✅ حذف شد.")
        return

    # کانال‌ها
    if data == "admin_add_channel":
        await db.set_fsm(user_id, "awaiting_channel")
        await query.edit_message_text("📢 آیدی کانال:")
        return
    if data == "admin_list_channels":
        channels = await db.get_all_channels()
        if not channels:
            await query.edit_message_text("📭 کانالی نیست.")
            return
        text = "📋 کانال‌ها:\n\n" + "\n".join(f"• `{c[1]}`" for c in channels)
        await query.edit_message_text(text)
        return
    if data == "admin_del_channel":
        channels = await db.get_all_channels()
        if not channels:
            await query.edit_message_text("📭 کانالی نیست.")
            return
        kb = [[InlineKeyboardButton(f"🗑 {c[1]}", callback_data=f"delch_{c[0]}")] for c in channels]
        await query.edit_message_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
        return
    if data.startswith("delch_"):
        cid = int(data.split("_")[1])
        await db.delete_channel(cid)
        await query.edit_message_text("✅ حذف شد.")
        return

    # VPN
    if data == "vpn_add":
        await db.set_fsm(user_id, "awaiting_vpn_content")
        await query.edit_message_text("🌐 محتوای فیلترشکن رو بفرست (عکس/متن/لینک/فوروارد...):")
        return
    if data == "vpn_list":
        links = await db.get_all_vpn_links()
        if not links:
            await query.edit_message_text("📭 لینکی نیست.")
            return
        text = "🌐 لینک‌های فیلترشکن:\n\n"
        for l in links:
            text += f"#{l[0]} | {l[1] or 'بدون اسم'}\n"
        await query.edit_message_text(text)
        return
    if data == "vpn_del":
        links = await db.get_all_vpn_links()
        if not links:
            await query.edit_message_text("📭 لینکی نیست.")
            return
        kb = [[InlineKeyboardButton(f"🗑 #{l[0]} | {l[1] or ''}", callback_data=f"vpndel_{l[0]}")] for l in links]
        await query.edit_message_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
        return
    if data.startswith("vpndel_"):
        vid = int(data.split("_")[1])
        await db.delete_vpn_link(vid)
        await query.edit_message_text("✅ حذف شد.")
        return

    # Custom Buttons
    if data == "cb_add":
        await db.set_fsm(user_id, "awaiting_cb_name")
        await query.edit_message_text("🎛 اسم دکمه رو بنویس:")
        return
    if data == "cb_list":
        cbs = await db.get_all_custom_buttons()
        if not cbs:
            await query.edit_message_text("📭 دکمه‌ای نیست.")
            return
        text = "🎛 دکمه‌های سفارشی:\n\n"
        for c in cbs:
            text += f"#{c[0]} | {c[1]}\n"
        await query.edit_message_text(text)
        return
    if data == "cb_del":
        cbs = await db.get_all_custom_buttons()
        if not cbs:
            await query.edit_message_text("📭 دکمه‌ای نیست.")
            return
        kb = [[InlineKeyboardButton(f"🗑 {c[1]}", callback_data=f"cbdel_{c[0]}")] for c in cbs]
        await query.edit_message_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
        return
    if data.startswith("cbdel_"):
        bid = int(data.split("_")[1])
        await db.delete_custom_button(bid)
        await query.edit_message_text("✅ حذف شد.")
        return

    # لینک یکبار مصرف
    if data == "otl_new":
        books = await db.get_all_books()
        if not books:
            await query.edit_message_text("📭 چیزی نیست.")
            return
        kb = [[InlineKeyboardButton(f"📖 {b[2]}", callback_data=f"otl_book_{b[0]}")] for b in books[:20]]
        await query.edit_message_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
        return
    if data.startswith("otl_book_"):
        bid = int(data.split("_")[2])
        await db.set_fsm(user_id, "otl_step1", {"book_id": bid})
        await query.edit_message_text("⏰ مدت اعتبار (ساعت) — مثال: `24` یا `0`:")
        return
    if data == "otl_list":
        links = await db.get_all_onetime_links()
        if not links:
            await query.edit_message_text("📭 لینکی نیست.")
            return
        text = "🔗 لینک‌ها:\n\n"
        for l in links[:20]:
            s = "✅" if l[3] else "🟢"
            text += f"{s} #{l[0]} | `{l[1]}` | #{l[2]}\n"
        await query.edit_message_text(text)
        return


# ═══════════ هندلر پیام ═══════════
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.message
    if not msg:
        return

    state, data = await db.get_fsm(user.id)

    # گروه
    if msg.chat.type in ("group", "supergroup"):
        if msg.text:
            try:
                reply = get_ready_reply(msg.chat_id, msg.text)
                if reply:
                    await msg.reply_text(reply)
            except Exception as e:
                logger.error(f"[AUTO-REPLY] {e}")
        return

    # چک عضویت
    if not is_admin(user.id):
        if not await is_user_joined(context, user.id):
            await send_join_prompt(update, context)
            return

    # ═══════════ کاربر ═══════════
    if msg.text == "📚 کتاب‌ها":
        cats = await db.get_all_categories()
        if not cats:
            await msg.reply_text("📭 ژانری نیست.")
            return
        kb = [[InlineKeyboardButton(f"📁 {c[1]}", callback_data=f"cat_{c[0]}_book")] for c in cats]
        await msg.reply_text("📚 ژانرها:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if msg.text == "📖 رمان‌ها":
        cats = await db.get_all_categories()
        if not cats:
            await msg.reply_text("📭 ژانری نیست.")
            return
        kb = [[InlineKeyboardButton(f"📁 {c[1]}", callback_data=f"cat_{c[0]}_novel")] for c in cats]
        await msg.reply_text("📚 ژانرها:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if msg.text == "🌐 فیلترشکن":
        links = await db.get_all_vpn_links()
        if not links:
            await msg.reply_text("📭 فعلاً چیزی نیست.")
            return
        # دکمه‌های 1 2 3
        kb = []
        row = []
        for i, l in enumerate(links, 1):
            row.append(InlineKeyboardButton(str(i), callback_data=f"vpn_{l[0]}"))
            if len(row) == 4:
                kb.append(row)
                row = []
        if row:
            kb.append(row)
        await msg.reply_text(
            f"🌐 لینک‌های فیلترشکن ({len(links)}):",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if msg.text == "🔍 جستجو":
        await db.set_fsm(user.id, "awaiting_search")
        await msg.reply_text(SEARCH_PROMPT)
        return

    if state == "awaiting_search":
        q = (msg.text or "").strip()
        if not q:
            await msg.reply_text("❌ چیزی بنویس.")
            return
        results = await db.search_books(q)
        if not results:
            await msg.reply_text(SEARCH_EMPTY)
        else:
            kb = []
            for r in results:
                prefix = "💳" if r[4] else "🆓"
                kb.append([InlineKeyboardButton(f"{prefix} {r[1]}", callback_data=f"book_{r[0]}")])
            await msg.reply_text(f"🔍 نتایج ({len(results)}):", reply_markup=InlineKeyboardMarkup(kb))
        await db.clear_fsm(user.id)
        return

    if msg.text == "⭐ امتیاز به ربات":
        if await db.has_rated(user.id):
            await msg.reply_text(RATING_ALREADY)
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐", callback_data="rate_1"),
             InlineKeyboardButton("⭐⭐", callback_data="rate_2"),
             InlineKeyboardButton("⭐⭐⭐", callback_data="rate_3")],
            [InlineKeyboardButton("⭐⭐⭐⭐", callback_data="rate_4"),
             InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data="rate_5")],
        ])
        await msg.reply_text(RATING_PROMPT, reply_markup=kb)
        return

    if state == "awaiting_rating_msg":
        if msg.text:
            await db.add_support_msg(user.id, user.username, user.first_name, f"[امتیاز] {msg.text}")
            try:
                await msg.forward(ADMIN_ID)
            except Exception:
                pass
        await msg.reply_text(RATING_MSG_SENT)
        await db.clear_fsm(user.id)
        return

    if msg.text == "📩 تماس با پشتیبانی":
        await db.set_fsm(user.id, "awaiting_support")
        await msg.reply_text(SUPPORT_PROMPT)
        return

    if state == "awaiting_support":
        if msg.text:
            await db.add_support_msg(user.id, user.username, user.first_name, msg.text)
        try:
            await msg.forward(ADMIN_ID)
        except Exception:
            pass
        await msg.reply_text(SUPPORT_SENT)
        await db.clear_fsm(user.id)
        return

    # دکمه سفارشی
    if msg.text and msg.text.startswith("🎯 "):
        name = msg.text[2:].strip()
        cbs = await db.get_all_custom_buttons()
        for c in cbs:
            if c[1] == name:
                try:
                    await send_captured(context, user.id, c[2])
                except Exception:
                    await msg.reply_text("❌ خطا در ارسال.")
                return
        return

    # ═══════════ ادمین ═══════════
    if is_admin(user.id):

        if msg.text and msg.text.startswith("reply_"):
            try:
                msg_id = int(msg.text.replace("reply_", "").strip())
            except Exception:
                await msg.reply_text("❌ مثال: reply_5")
                return
            s_msg = await db.get_support_msg(msg_id)
            if not s_msg:
                await msg.reply_text("❌ پیدا نشد.")
                return
            sid, uid, fname, txt = s_msg
            await db.set_fsm(user.id, "awaiting_reply_text", {"target": uid, "msg_id": msg_id})
            await msg.reply_text(f"✏️ جواب به {fname}:\n\n💬 {txt[:50]}")
            return

        if state == "awaiting_reply_text":
            target = data.get("target")
            msg_id = data.get("msg_id")
            if target and msg.text:
                try:
                    await context.bot.send_message(target, f"📩 پاسخ:\n\n{msg.text}")
                    await msg.reply_text("✅ فرستاده شد.")
                    if msg_id:
                        await db.mark_support_seen(msg_id)
                except Exception as e:
                    await msg.reply_text(f"❌ {e}")
            await db.clear_fsm(user.id)
            return

        # پنل پیام‌ها
        if msg.text == "📩 پنل پیام‌ها":
            msgs = await db.get_all_support_msgs(30)
            if not msgs:
                await msg.reply_text("📭 پیامی نیست.")
                return
            text = f"📩 پیام‌ها ({len(msgs)}):\n\n"
            for m in msgs[:15]:
                status = "✅" if m[4] else "🆕"
                text += f"{status} #{m[0]} | {m[2]}\n💬 {m[3][:50]}\n\n"
            text += "جواب: `reply_شماره`"
            await msg.reply_text(text)
            return

        # امتیازها
        if msg.text == "⭐ امتیازها":
            avg, count = await db.get_rating_stats()
            ratings = await db.get_all_ratings()
            text = f"⭐ امتیازها\n\nمیانگین: {avg}\nتعداد: {count}\n\n"
            for r in ratings[:10]:
                text += f"⭐ {r[3]} | {r[2]}"
                if r[4]:
                    text += f"\n💬 {r[4][:40]}"
                text += "\n\n"
            await msg.reply_text(text)
            return

        # ژانرها
        if msg.text == "📁 ژانرها":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ افزودن", callback_data="newcat")],
                [InlineKeyboardButton("📋 لیست", callback_data="admin_list_cats")],
                [InlineKeyboardButton("🗑 حذف", callback_data="admin_del_cat")],
            ])
            await msg.reply_text("📁 ژانرها:", reply_markup=kb)
            return

        # رمان‌ها
        if msg.text == "📖 رمان‌ها":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 PDF کلی", callback_data="novel_menu_pdf_full")],
                [InlineKeyboardButton("📑 PDF صفحه‌ای", callback_data="novel_menu_pdf_pages")],
                [InlineKeyboardButton("📝 نوشته‌ای", callback_data="novel_menu_text")],
            ])
            await msg.reply_text("📖 رمان‌ها:", reply_markup=kb)
            return

        # کتاب‌ها
        if msg.text == "📚 کتاب‌ها":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 PDF کلی", callback_data="book_menu_pdf_full")],
                [InlineKeyboardButton("📑 PDF صفحه‌ای", callback_data="book_menu_pdf_pages")],
                [InlineKeyboardButton("📝 نوشته‌ای", callback_data="book_menu_text")],
            ])
            await msg.reply_text("📚 کتاب‌ها:", reply_markup=kb)
            return

        # کانال‌ها
        if msg.text == "📢 کانال‌ها":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ افزودن", callback_data="admin_add_channel")],
                [InlineKeyboardButton("📋 لیست", callback_data="admin_list_channels")],
                [InlineKeyboardButton("🗑 حذف", callback_data="admin_del_channel")],
            ])
            await msg.reply_text("📢 کانال‌ها:", reply_markup=kb)
            return

        # VPN
        if msg.text == "🌐 فیلترشکن":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ افزودن", callback_data="vpn_add")],
                [InlineKeyboardButton("📋 لیست", callback_data="vpn_list")],
                [InlineKeyboardButton("🗑 حذف", callback_data="vpn_del")],
            ])
            await msg.reply_text("🌐 فیلترشکن:", reply_markup=kb)
            return

        # دکمه‌های سفارشی
        if msg.text == "🎛 دکمه‌های سفارشی":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ افزودن", callback_data="cb_add")],
                [InlineKeyboardButton("📋 لیست", callback_data="cb_list")],
                [InlineKeyboardButton("🗑 حذف", callback_data="cb_del")],
            ])
            await msg.reply_text("🎛 دکمه‌های سفارشی:", reply_markup=kb)
            return

        # تنظیمات
        if msg.text == "⚙️ تنظیمات":
            req = await db.get_setting("reaction_required", "5")
            days = await db.get_setting("inactive_days", "25")
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"⚡ ری‌اکشن اجباری: {req}", callback_data="set_reaction")],
                [InlineKeyboardButton(f"⏰ روز غیرفعال: {days}", callback_data="set_inactive")],
            ])
            await msg.reply_text("⚙️ تنظیمات:", reply_markup=kb)
            return

        if data_ := None:
            pass

        # کاربران غیرفعال
        if msg.text == "👥 کاربران غیرفعال":
            days = int(await db.get_setting("inactive_days", "25") or 25)
            users = await db.get_inactive_users(days)
            if not users:
                await msg.reply_text(f"📭 کاربری نیست ({days} روز).")
                return
            text = f"👥 غیرفعال ({days} روز) — {len(users)} نفر:\n\n"
            for u in users[:30]:
                text += f"👤 {u[2]} | `{u[0]}` | @{u[1] or 'ندارد'}\n"
            await msg.reply_text(text)
            return

        # ═══════════ FSM ═══════════
        if state == "awaiting_cat_name":
            data["name"] = msg.text or ""
            await db.set_fsm(user.id, "awaiting_cat_desc", data)
            await msg.reply_text("📝 توضیحات (یا `skip`):")
            return
        if state == "awaiting_cat_desc":
            data["description"] = "" if (msg.text and msg.text.lower() == "skip") else (msg.text or "")
            await db.set_fsm(user.id, "awaiting_cat_banner", data)
            await msg.reply_text("🖼 بنر (یا `skip`):")
            return
        if state == "awaiting_cat_banner":
            banner = None if (msg.text and msg.text.lower() == "skip") else capture_message(msg)
            cid = await db.add_category(data["name"], data.get("description", ""), banner)
            await db.clear_fsm(user.id)
            await msg.reply_text(f"✅ ژانر ساخته شد. (#{cid})")
            return

        # افزودن کتاب
        if state == "awaiting_book_name_fa":
            data["title_fa"] = msg.text or ""
            await db.set_fsm(user.id, "awaiting_book_name_en", data)
            await msg.reply_text("📕 اسم انگلیسی (یا `skip`):")
            return
        if state == "awaiting_book_name_en":
            data["title_en"] = "" if (msg.text and msg.text.lower() == "skip") else (msg.text or "")
            await db.set_fsm(user.id, "awaiting_book_author", data)
            await msg.reply_text("✍️ نویسنده (یا `skip`):")
            return
        if state == "awaiting_book_author":
            data["author"] = "" if (msg.text and msg.text.lower() == "skip") else (msg.text or "")
            await db.set_fsm(user.id, "awaiting_book_translator", data)
            await msg.reply_text("🖋 مترجم (یا `skip`):")
            return
        if state == "awaiting_book_translator":
            data["translator"] = "" if (msg.text and msg.text.lower() == "skip") else (msg.text or "")
            await db.set_fsm(user.id, "awaiting_book_desc", data)
            await msg.reply_text("📝 توضیحات (یا `skip`):")
            return
        if state == "awaiting_book_desc":
            data["description"] = "" if (msg.text and msg.text.lower() == "skip") else (msg.text or "")
            await db.set_fsm(user.id, "awaiting_book_paid", data)
            await msg.reply_text("💰 `پولی` یا `رایگان`؟")
            return
        if state == "awaiting_book_paid":
            txt = (msg.text or "").strip()
            if txt == "پولی":
                data["is_paid"] = 1
                await db.set_fsm(user.id, "awaiting_book_price", data)
                await msg.reply_text("💵 قیمت:")
                return
            else:
                data["is_paid"] = 0
                data["price"] = ""
                await db.set_fsm(user.id, "awaiting_book_banner", data)
                await msg.reply_text("🖼 بنر (یا `skip`):")
                return
        if state == "awaiting_book_price":
            data["price"] = msg.text or ""
            await db.set_fsm(user.id, "awaiting_book_banner", data)
            await msg.reply_text("🖼 بنر (یا `skip`):")
            return
        if state == "awaiting_book_banner":
            banner = None if (msg.text and msg.text.lower() == "skip") else capture_message(msg)
            bid = await db.add_book(
                data.get("kind", "novel"),
                data["category_id"], data["title_fa"], data.get("title_en", ""),
                data.get("author", ""), data.get("translator", ""), data.get("description", ""),
                None, data.get("book_type", "pdf_full"), data.get("is_paid", 0),
                data.get("price", ""), banner
            )
            data["book_id"] = bid
            btype = data.get("book_type")
            if btype == "pdf_full":
                await db.set_fsm(user.id, "awaiting_pdf_file", data)
                await msg.reply_text("📄 فایل PDF کامل:")
            elif btype == "pdf_pages":
                await db.set_fsm(user.id, "awaiting_pdf_pages", data)
                await msg.reply_text("📑 صفحه PDF اول (پایان: `done`):")
            elif btype == "text":
                await db.set_fsm(user.id, "awaiting_text_pages", data)
                await msg.reply_text("📝 متن صفحه ۱ (پایان: `done`):")
            return

        if state == "awaiting_pdf_file":
            file_id = msg.document.file_id if msg.document else None
            if file_id:
                await db.add_book_file(data["book_id"], "📄 PDF", file_id)
                await db.clear_fsm(user.id)
                await msg.reply_text(f"✅ کامل شد. (#{data['book_id']})")
            else:
                await msg.reply_text("❌ فایل PDF نفرستادی.")
            return

        if state == "awaiting_pdf_pages":
            if msg.text and msg.text.strip().lower() == "done":
                await db.clear_fsm(user.id)
                await msg.reply_text(f"✅ کامل شد. (#{data['book_id']})")
                return
            file_id = msg.document.file_id if msg.document else None
            if file_id:
                bid = data["book_id"]
                pages = await db.get_pages(bid)
                next_num = len(pages) + 1
                await db.add_page(bid, next_num, None, file_id)
                await msg.reply_text(f"✅ صفحه {next_num}. بعدی یا `done`:")
            else:
                await msg.reply_text("❌ فایل PDF صفحه رو بفرست.")
            return

        if state == "awaiting_text_pages":
            if msg.text and msg.text.strip().lower() == "done":
                await db.clear_fsm(user.id)
                await msg.reply_text(f"✅ کامل شد. (#{data['book_id']})")
                return
            if msg.text:
                bid = data["book_id"]
                pages = await db.get_pages(bid)
                next_num = len(pages) + 1
                await db.add_page(bid, next_num, msg.text, None)
                await msg.reply_text(f"✅ صفحه {next_num}. بعدی یا `done`:")
            return

        if state == "awaiting_channel":
            try:
                chat = await context.bot.get_chat(msg.text.strip())
                invite = f"https://t.me/{chat.username}" if chat.username else chat.invite_link
                await db.add_channel(str(chat.id), "عضویت", invite)
                await msg.reply_text("✅ کانال اضافه شد.")
            except Exception as e:
                await msg.reply_text(f"❌ {e}")
            await db.clear_fsm(user.id)
            return

        # VPN
        if state == "awaiting_vpn_content":
            mjson = capture_message(msg)
            label = msg.text[:30] if msg.text else "لینک"
            await db.add_vpn_link(label, mjson)
            await db.clear_fsm(user.id)
            await msg.reply_text("✅ لینک اضافه شد.")
            return

        # Custom Button
        if state == "awaiting_cb_name":
            data["name"] = msg.text or ""
            await db.set_fsm(user.id, "awaiting_cb_content", data)
            await msg.reply_text("🎛 محتوای دکمه رو بفرست:")
            return
        if state == "awaiting_cb_content":
            mjson = capture_message(msg)
            await db.add_custom_button(data["name"], mjson)
            await db.clear_fsm(user.id)
            await msg.reply_text(f"✅ دکمه «{data['name']}» اضافه شد.")
            return

        # تنظیمات
        if state == "awaiting_reaction_set":
            try:
                n = int(msg.text.strip())
                await db.set_setting("reaction_required", str(n))
                await msg.reply_text(f"✅ تعداد ری‌اکشن: {n}")
            except Exception:
                await msg.reply_text("❌ عدد بفرست.")
            await db.clear_fsm(user.id)
            return
        if state == "awaiting_inactive_set":
            try:
                n = int(msg.text.strip())
                await db.set_setting("inactive_days", str(n))
                await msg.reply_text(f"✅ روز غیرفعال: {n}")
            except Exception:
                await msg.reply_text("❌ عدد بفرست.")
            await db.clear_fsm(user.id)
            return

        # بنر
        if msg.text == "📢 بنر فوری":
            await db.set_fsm(user.id, "awaiting_instant_banner")
            await msg.reply_text("📢 بنر رو بفرست.\n\nبعد: `ارسال بنر فوری`")
            return
        if state == "awaiting_instant_banner":
            await db.set_instant_banner(capture_message(msg))
            await msg.reply_text("✅ تنظیم شد.\n\n`ارسال بنر فوری`")
            await db.clear_fsm(user.id)
            return
        if msg.text == "ارسال بنر فوری":
            count = await broadcast_instant_banner(context)
            await msg.reply_text(f"✅ ارسال شد به {count} کاربر." if count else "❌ بنری نیست.")
            return

        # بنر زمان‌بندی
        if msg.text == "⏰ بنر زمان‌بندی":
            await db.set_fsm(user.id, "awaiting_sched_banner_content")
            await msg.reply_text("⏰ محتوا:")
            return
        if state == "awaiting_sched_banner_content":
            data["message_json"] = capture_message(msg)
            await db.set_fsm(user.id, "awaiting_sched_banner_time", data)
            await msg.reply_text("✅ ثبت شد.\n\nزمان: `2026-10-01 20:30` یا شمسی `1404-07-15 20:30`")
            return
        if state == "awaiting_sched_banner_time":
            run_at = parse_datetime(msg.text.strip())
            if not run_at:
                await msg.reply_text("❌ فرمت اشتباه.")
                return
            await db.add_scheduled_banner(data["message_json"], run_at)
            await db.clear_fsm(user.id)
            await msg.reply_text(f"✅ زمان‌بندی شد! 📅 {run_at[:16]}")
            return

        if msg.text == "📋 لیست بنرها":
            banners = await db.get_all_scheduled_banners()
            if not banners:
                await msg.reply_text("📭 بنری نیست.")
                return
            text = "📋 بنرها:\n\n"
            for b in banners[:20]:
                s = "✅" if b[3] else "⏳"
                text += f"{s} #{b[0]} | {b[2][:16]}\n"
            text += "\nحذف: `حذف بنر 5`"
            await msg.reply_text(text)
            return

        if msg.text and msg.text.startswith("حذف بنر "):
            try:
                bid = int(msg.text.replace("حذف بنر ", "").strip())
                await db.delete_scheduled_banner(bid)
                await msg.reply_text(f"✅ بنر #{bid} حذف شد.")
            except Exception:
                await msg.reply_text("❌ فرمت اشتباه.")
            return

        # لینک
        if msg.text == "🔗 لینک یکبار مصرف":
            links = await db.get_all_onetime_links()
            kb = [
                [InlineKeyboardButton("➕ ساخت", callback_data="otl_new")],
                [InlineKeyboardButton("📋 لیست", callback_data="otl_list")],
            ]
            await msg.reply_text(f"🔗 لینک‌ها ({len(links)}):", reply_markup=InlineKeyboardMarkup(kb))
            return

        if state == "otl_step1":
            try:
                hours = int(msg.text.strip())
            except Exception:
                await msg.reply_text("❌ عدد بفرست.")
                return
            bid = data.get("book_id")
            code = await create_onetime_link(bid, hours)
            bot_info = await context.bot.get_me()
            link = await generate_bot_link(bot_info.username, code)
            await db.clear_fsm(user.id)
            expire_text = f"{hours} ساعت" if hours > 0 else "بدون انقضا"
            await msg.reply_text(f"✅ ساخته شد!\n\n#{bid}\n⏰ {expire_text}\n\n🔗 `{link}`")
            return

        # آمار
        if msg.text == "📊 آمار ربات":
            users = await db.get_users_count()
            cats = await db.get_all_categories()
            novels = await db.get_all_books("novel")
            books = await db.get_all_books("book")
            channels = await db.get_all_channels()
            vpns = await db.get_all_vpn_links()
            cbs = await db.get_all_custom_buttons()
            links = await db.get_all_onetime_links()
            support_count = await db.get_support_count()
            avg, count = await db.get_rating_stats()
            text = (
                f"📊 آمار\n\n"
                f"👥 کاربران: {users}\n"
                f"📁 ژانرها: {len(cats)}\n"
                f"📖 رمان‌ها: {len(novels)}\n"
                f"📚 کتاب‌ها: {len(books)}\n"
                f"📢 کانال‌ها: {len(channels)}\n"
                f"🌐 فیلترشکن: {len(vpns)}\n"
                f"🎛 دکمه سفارشی: {len(cbs)}\n"
                f"🔗 لینک‌ها: {len(links)}\n"
                f"📩 پیام‌ها: {support_count}\n"
                f"⭐ امتیاز: {avg} ({count})"
            )
            await msg.reply_text(text)
            return

    if msg.photo or msg.video or msg.document or msg.audio or msg.voice or msg.animation:
        await msg.reply_text(FILE_SENT)
        return

    await msg.reply_text(FILE_NOT_FOUND)


# ═══════════ Post Init ═══════════
async def post_init(app):
    await db.init_db()
    asyncio.create_task(process_scheduled_banners(app))
    asyncio.create_task(process_inactive_users(app))


# ═══════════ اجرا ═══════════
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN نیست!")
        return
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))
    print("🚀 ربات روشن شد...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
