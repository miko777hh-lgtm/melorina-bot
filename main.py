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
from scheduler import process_scheduled_banners
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
    if kind == "novel":
        return {"text": "📝", "pdf_full": "📄", "pdf_pages": "📑"}.get(btype, "📖")
    return {"text": "📝", "pdf_full": "📄", "pdf_pages": "📑"}.get(btype, "📚")


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

    await update.message.reply_text(WELCOME_AFTER_JOIN, reply_markup=user_reply_keyboard())


# ═══════════ ارسال محتوا به کاربر ═══════════
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

    # اطلاعات اضافی
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

    # ═══════════ کاربر: ژانرها (رمان) ═══════════
    if data == "user_cats_novel":
        cats = await db.get_all_categories()
        if not cats:
            await query.edit_message_text("📭 ژانری نیست.")
            return
        kb = [[InlineKeyboardButton(f"📁 {c[1]}", callback_data=f"cat_{c[0]}_novel")] for c in cats]
        await query.edit_message_text("📚 ژانرها (رمان):", reply_markup=InlineKeyboardMarkup(kb))
        return

    # ═══════════ کاربر: ژانرها (کتاب) ═══════════
    if data == "user_cats_book":
        cats = await db.get_all_categories()
        if not cats:
            await query.edit_message_text("📭 ژانری نیست.")
            return
        kb = [[InlineKeyboardButton(f"📁 {c[1]}", callback_data=f"cat_{c[0]}_book")] for c in cats]
        await query.edit_message_text("📚 ژانرها (کتاب):", reply_markup=InlineKeyboardMarkup(kb))
        return

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

    # ═══════════ کاربر: انتخاب رمان/کتاب ═══════════
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

        # پولی → پیام به آیدی
        if is_paid == 1:
            info += f"\n💳 قیمت: {price or 'تماس با ادمین'}\n\n"
            info += "برای خرید به آیدی زیر پیام بده:\n👤 @Yuriii79"
            kb = [[InlineKeyboardButton("📩 خرید", url="https://t.me/Yuriii79")]]
            await query.edit_message_text(info, reply_markup=InlineKeyboardMarkup(kb))
            return

        # رایگان
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

        # اطلاعات اضافی
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
                await context.bot.send_message(user_id, f"خطا در ارسال صفحه {page_num}")
        return

    # ═══════════ امتیازدهی ═══════════
    if data.startswith("rate_"):
        rating = int(data.split("_")[1])
        await db.add_rating(user_id, query.from_user.username, query.from_user.first_name, rating, None)
        await query.edit_message_text(
            f"⭐ امتیازت ثبت شد: {'⭐' * rating}\n\nاگه حرفی با ادمین داری، همین‌جا بنویس 👇"
        )
        await db.set_fsm(user_id, "awaiting_rating_msg")
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"⭐ امتیاز جدید\n\n"
                f"👤 {query.from_user.first_name}\n"
                f"🆔 `{query.from_user.id}`\n"
                f"📛 @{query.from_user.username or 'ندارد'}\n"
                f"⭐ {rating} از ۵",
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

    # ═══════════ ژانرها ═══════════
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

    # ═══════════ منوی رمان‌ها (ادمین) ═══════════
    if data == "admin_novel_menu":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 رمان PDF کلی", callback_data="novel_menu_pdf_full")],
            [InlineKeyboardButton("📑 رمان PDF صفحه‌ای", callback_data="novel_menu_pdf_pages")],
            [InlineKeyboardButton("📝 رمان نوشته‌ای", callback_data="novel_menu_text")],
        ])
        await query.edit_message_text("📖 رمان‌ها:", reply_markup=kb)
        return

    if data.startswith("novel_menu_"):
        btype = data.replace("novel_menu_", "")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ افزودن", callback_data=f"newbook_novel_{btype}")],
            [InlineKeyboardButton("📋 لیست", callback_data=f"list_{btype}_novel")],
            [InlineKeyboardButton("🗑 حذف", callback_data=f"delbooks_{btype}_novel")],
        ])
        await query.edit_message_text(f"📖 مدیریت رمان:", reply_markup=kb)
        return

    # ═══════════ منوی کتاب‌ها (ادمین) ═══════════
    if data == "admin_book_menu":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 کتاب PDF کلی", callback_data="book_menu_pdf_full")],
            [InlineKeyboardButton("📑 کتاب PDF صفحه‌ای", callback_data="book_menu_pdf_pages")],
            [InlineKeyboardButton("📝 کتاب نوشته‌ای", callback_data="book_menu_text")],
        ])
        await query.edit_message_text("📚 کتاب‌ها:", reply_markup=kb)
        return

    if data.startswith("book_menu_"):
        btype = data.replace("book_menu_", "")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ افزودن", callback_data=f"newbook_book_{btype}")],
            [InlineKeyboardButton("📋 لیست", callback_data=f"list_{btype}_book")],
            [InlineKeyboardButton("🗑 حذف", callback_data=f"delbooks_{btype}_book")],
        ])
        await query.edit_message_text(f"📚 مدیریت کتاب:", reply_markup=kb)
        return

    # ═══════════ انتخاب ژانر برای افزودن ═══════════
    if data.startswith("newbook_"):
        parts = data.split("_")
        kind = parts[1]  # novel or book
        btype = "_".join(parts[2:])  # pdf_full, pdf_pages, text
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

    # ═══════════ لیست/حذف ═══════════
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
            bid, tfa, ten, bt, is_paid, price = b
            t = "💳" if is_paid else "🆓"
            text += f"#{bid} | {t} {tfa}\n"
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

    # ═══════════ کانال ═══════════
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

    # ═══════════ لینک یکبار مصرف ═══════════
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
            lid, code, bid, used, exp, created = l
            s = "✅" if used else "🟢"
            text += f"{s} #{lid} | `{code}` | #{bid}\n"
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

    # چت خصوصی — چک عضویت
    if not is_admin(user.id):
        if not await is_user_joined(context, user.id):
            await send_join_prompt(update, context)
            return

    # ═══════════ کاربر: کتاب‌ها ═══════════
    if msg.text == "📚 کتاب‌ها":
        cats = await db.get_all_categories()
        if not cats:
            await msg.reply_text("📭 ژانری نیست.")
            return
        kb = [[InlineKeyboardButton(f"📁 {c[1]}", callback_data=f"cat_{c[0]}_book")] for c in cats]
        await msg.reply_text("📚 ژانرها:", reply_markup=InlineKeyboardMarkup(kb))
        return

    # ═══════════ کاربر: رمان‌ها ═══════════
    if msg.text == "📖 رمان‌ها":
        cats = await db.get_all_categories()
        if not cats:
            await msg.reply_text("📭 ژانری نیست.")
            return
        kb = [[InlineKeyboardButton(f"📁 {c[1]}", callback_data=f"cat_{c[0]}_novel")] for c in cats]
        await msg.reply_text("📚 ژانرها:", reply_markup=InlineKeyboardMarkup(kb))
        return

    # ═══════════ کاربر: جستجو ═══════════
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
                rid, tfa, ten, btype, is_paid = r
                prefix = "💳" if is_paid else "🆓"
                kb.append([InlineKeyboardButton(f"{prefix} {tfa}", callback_data=f"book_{rid}")])
            await msg.reply_text(
                f"🔍 نتایج ({len(results)}):",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        await db.clear_fsm(user.id)
        return

    # ═══════════ کاربر: امتیاز ═══════════
    if msg.text == "⭐ امتیاز به ربات":
        if await db.has_rated(user.id):
            await msg.reply_text(RATING_ALREADY)
            return
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⭐", callback_data="rate_1"),
                InlineKeyboardButton("⭐⭐", callback_data="rate_2"),
                InlineKeyboardButton("⭐⭐⭐", callback_data="rate_3"),
            ],
            [
                InlineKeyboardButton("⭐⭐⭐⭐", callback_data="rate_4"),
                InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data="rate_5"),
            ]
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

    # ═══════════ کاربر: پشتیبانی ═══════════
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

    # ═══════════ ادمین ═══════════
    if is_admin(user.id):

        # reply_X
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
                    await context.bot.send_message(target, f"📩 پاسخ پشتیبانی:\n\n{msg.text}")
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
                mid, uid, fname, txt, seen, created = m
                status = "✅" if seen else "🆕"
                text += f"{status} #{mid} | {fname}\n💬 {txt[:50]}\n\n"
            text += "برای جواب: `reply_شماره`"
            await msg.reply_text(text)
            return

        # امتیازها
        if msg.text == "⭐ امتیازها":
            avg, count = await db.get_rating_stats()
            ratings = await db.get_all_ratings()
            text = f"⭐ امتیازها\n\nمیانگین: {avg}\nتعداد: {count}\n\n"
            if ratings:
                text += "آخرین:\n"
                for r in ratings[:10]:
                    rid, uid, fname, rate, message, created = r
                    text += f"⭐ {rate} | {fname}"
                    if message:
                        text += f"\n💬 {message[:40]}"
                    text += "\n\n"
            await msg.reply_text(text)
            return

        # ژانرها
        if msg.text == "📁 ژانرها":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ افزودن ژانر", callback_data="newcat")],
                [InlineKeyboardButton("📋 لیست ژانرها", callback_data="admin_list_cats")],
                [InlineKeyboardButton("🗑 حذف ژانر", callback_data="admin_del_cat")],
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
            await msg.reply_text("📖 مدیریت رمان‌ها:", reply_markup=kb)
            return

        # کتاب‌ها
        if msg.text == "📚 کتاب‌ها":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 PDF کلی", callback_data="book_menu_pdf_full")],
                [InlineKeyboardButton("📑 PDF صفحه‌ای", callback_data="book_menu_pdf_pages")],
                [InlineKeyboardButton("📝 نوشته‌ای", callback_data="book_menu_text")],
            ])
            await msg.reply_text("📚 مدیریت کتاب‌ها:", reply_markup=kb)
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

        # ═══════════ FSM: افزودن ژانر ═══════════
        if state == "awaiting_cat_name":
            data["name"] = msg.text or ""
            await db.set_fsm(user.id, "awaiting_cat_desc", data)
            await msg.reply_text("📝 توضیحات (یا `skip`):")
            return

        if state == "awaiting_cat_desc":
            txt = msg.text or ""
            data["description"] = "" if txt.lower() == "skip" else txt
            await db.set_fsm(user.id, "awaiting_cat_banner", data)
            await msg.reply_text("🖼 بنر ژانر (یا `skip`):")
            return

        if state == "awaiting_cat_banner":
            banner = None if (msg.text and msg.text.lower() == "skip") else capture_message(msg)
            cid = await db.add_category(data["name"], data.get("description", ""), banner)
            await db.clear_fsm(user.id)
            await msg.reply_text(f"✅ ژانر ساخته شد. (#{cid})")
            return

        # ═══════════ FSM: افزودن رمان/کتاب ═══════════
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
            await msg.reply_text("💰 پولی؟ (`پولی` یا `رایگان`):")
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
                await msg.reply_text("📄 فایل PDF کامل رو بفرست:")
            elif btype == "pdf_pages":
                await db.set_fsm(user.id, "awaiting_pdf_pages", data)
                await msg.reply_text("📑 صفحه PDF اول (پایان: `done`):")
            elif btype == "text":
                await db.set_fsm(user.id, "awaiting_text_pages", data)
                await msg.reply_text("📝 متن صفحه ۱ (پایان: `done`):")
            return

        # ─── PDF کلی ───
        if state == "awaiting_pdf_file":
            file_id = msg.document.file_id if msg.document else None
            if file_id:
                bid = data["book_id"]
                await db.add_book_file(bid, "📄 PDF", file_id)
                await db.clear_fsm(user.id)
                await msg.reply_text(f"✅ کامل شد. (#{bid})")
            else:
                await msg.reply_text("❌ فایل PDF نفرستادی.")
            return

        # ─── PDF صفحه‌ای ───
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
                await msg.reply_text(f"✅ صفحه {next_num} ذخیره شد. بعدی یا `done`:")
            else:
                await msg.reply_text("❌ فایل PDF صفحه رو بفرست.")
            return

        # ─── متن ───
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
                await msg.reply_text(f"✅ صفحه {next_num} ذخیره شد. بعدی یا `done`:")
            return

        # ═══════════ افزودن اطلاعات (فقط برای کتاب) ═══════════
        if state == "awaiting_book_info":
            bid = data.get("book_id")
            if bid and msg.text and msg.text.strip().lower() == "done":
                await db.clear_fsm(user.id)
                await msg.reply_text("✅ اطلاعات ذخیره شد.")
                return
            if bid:
                await db.add_book_info(bid, capture_message(msg))
                await msg.reply_text("✅ ثبت شد. بعدی یا `done`:")
            return

        # ═══════════ FSM: افزودن کانال ═══════════
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

        # ═══════════ بنر فوری ═══════════
        if msg.text == "📢 بنر فوری":
            await db.set_fsm(user.id, "awaiting_instant_banner")
            await msg.reply_text("📢 بنر فوری رو بفرست.\n\nبعد بنویس: `ارسال بنر فوری`")
            return

        if state == "awaiting_instant_banner":
            await db.set_instant_banner(capture_message(msg))
            await msg.reply_text("✅ تنظیم شد.\n\nبنویس: `ارسال بنر فوری`")
            await db.clear_fsm(user.id)
            return

        if msg.text == "ارسال بنر فوری":
            count = await broadcast_instant_banner(context)
            await msg.reply_text(f"✅ ارسال شد به {count} کاربر." if count else "❌ بنری تنظیم نشده.")
            return

        # ═══════════ بنر زمان‌بندی ═══════════
        if msg.text == "⏰ بنر زمان‌بندی":
            await db.set_fsm(user.id, "awaiting_sched_banner_content")
            await msg.reply_text("⏰ محتوا رو بفرست:")
            return

        if state == "awaiting_sched_banner_content":
            data["message_json"] = capture_message(msg)
            await db.set_fsm(user.id, "awaiting_sched_banner_time", data)
            await msg.reply_text("✅ ثبت شد.\n\nزمان:\nمیلادی: `2026-10-01 20:30`\nشمسی: `1404-07-15 20:30`")
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
                bid, mjson, run_at, sent = b
                s = "✅" if sent else "⏳"
                text += f"{s} #{bid} | {run_at[:16]}\n"
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

        # ═══════════ لینک یکبار مصرف ═══════════
        if msg.text == "🔗 لینک یکبار مصرف":
            links = await db.get_all_onetime_links()
            kb = [
                [InlineKeyboardButton("➕ ساخت لینک", callback_data="otl_new")],
                [InlineKeyboardButton("📋 لیست لینک‌ها", callback_data="otl_list")],
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
            await msg.reply_text(
                f"✅ لینک ساخته شد!\n\n"
                f"#{bid}\n⏰ {expire_text}\n\n"
                f"🔗 `{link}`"
            )
            return

        # ═══════════ آمار ═══════════
        if msg.text == "📊 آمار ربات":
            users = await db.get_users_count()
            cats = await db.get_all_categories()
            novels = await db.get_all_books("novel")
            books = await db.get_all_books("book")
            channels = await db.get_all_channels()
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
