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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
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


# ═══════════ کیبورد صفحات (6 تا 6 تا) ═══════════
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
        # ارسال کتاب به کاربر
        await send_book_to_user(context, user.id, result["book_id"])
        return

    if is_admin(user.id):
        await show_admin_panel(update, context)
        return

    if not await is_user_joined(context, user.id):
        await send_join_prompt(update, context)
        return

    await update.message.reply_text(
        WELCOME_AFTER_JOIN,
        reply_markup=user_reply_keyboard()
    )


# ═══════════ ارسال کتاب به کاربر ═══════════
async def send_book_to_user(context, chat_id, book_id):
    """ارسال کامل کتاب (متن یا فایل)"""
    book = await db.get_book(book_id)
    if not book:
        await context.bot.send_message(chat_id, "کتاب پیدا نشد.")
        return

    b_id, cat_id, title_fa, title_en, author, translator, desc, cover, btype, is_paid, price, preview, banner = book

    # هدر
    header = f"📖 {title_fa}\n"
    if title_en:
        header += f"📕 {title_en}\n"
    if author:
        header += f"✍️ {author}\n"
    if translator:
        header += f"🖋 مترجم: {translator}\n"
    header += "\n"

    if btype == "text":
        # رمان متنی — لیست صفحات
        pages = await db.get_pages(b_id)
        if not pages:
            await context.bot.send_message(chat_id, "📭 صفحه‌ای نیست.")
            return
        await context.bot.send_message(
            chat_id,
            header + "صفحه موردنظر رو انتخاب کن:",
            reply_markup=pages_keyboard(b_id, len(pages))
        )

    elif btype == "pdf":
        # رمان PDF
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

    elif btype == "both":
        # هردو — کاربر انتخاب کنه
        text_pages = await db.get_pages(b_id)
        files = await db.get_book_files(b_id)
        kb = []
        if text_pages:
            kb.append([InlineKeyboardButton("📱 نسخه متنی", callback_data=f"open_text_{b_id}")])
        if files:
            kb.append([InlineKeyboardButton("📄 نسخه PDF", callback_data=f"open_pdf_{b_id}")])
        if not kb:
            await context.bot.send_message(chat_id, "📭 محتوایی نیست.")
            return
        await context.bot.send_message(
            chat_id,
            header + "کدوم نسخه رو می‌خوای؟",
            reply_markup=InlineKeyboardMarkup(kb)
        )


# ═══════════ کال‌بک ═══════════
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # ═══════════ بررسی عضویت ═══════════
    if data == "check_join":
        await check_join_callback(update, context)
        return

    # ═══════════ منوی ژانرها (کاربر) ═══════════
    if data == "user_categories":
        cats = await db.get_all_categories()
        if not cats:
            await query.edit_message_text("📭 هنوز ژانری اضافه نشده.")
            return
        kb = []
        for c in cats:
            cid, cname, cdesc, cbanner = c
            kb.append([InlineKeyboardButton(f"📁 {cname}", callback_data=f"cat_{cid}")])
        await query.edit_message_text("📚 ژانرها:\n\nیکی رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("cat_"):
        cid = int(data.split("_")[1])
        books = await db.get_books_by_category(cid)
        if not books:
            await query.edit_message_text("📭 تو این ژانر کتابی نیست.")
            return
        kb = []
        for b in books:
            bid, tfa, ten, btype, is_paid, price = b
            prefix = "💳" if is_paid else "🆓"
            kb.append([InlineKeyboardButton(f"{prefix} {tfa}", callback_data=f"book_{bid}")])
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="user_categories")])
        await query.edit_message_text("📚 کتاب‌ها:\n\nیکی رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("book_"):
        bid = int(data.split("_")[1])
        book = await db.get_book(bid)
        if not book:
            await query.edit_message_text(BOOK_NOT_FOUND)
            return

        b_id, cat_id, title_fa, title_en, author, translator, desc, cover, btype, is_paid, price, preview, banner = book

        # پیام اطلاعات
        info = f"📖 {title_fa}\n"
        if title_en:
            info += f"📕 {title_en}\n"
        if author:
            info += f"✍️ {author}\n"
        if translator:
            info += f"🖋 مترجم: {translator}\n"
        if desc:
            info += f"\n📝 {desc}\n"

        # پولی
        if is_paid == 1:
            info += f"\n💳 قیمت: {price or 'تماس با ادمین'}\n\nبرای خرید، به ادمین پیام بده."
            kb = [[InlineKeyboardButton("📩 خرید از ادمین", callback_data=f"buy_{bid}")]]
            await query.edit_message_text(info, reply_markup=InlineKeyboardMarkup(kb))
            return

        # رایگان
        if btype == "text":
            pages = await db.get_pages(b_id)
            if not pages:
                await query.edit_message_text("📭 صفحه‌ای نیست.")
                return
            await query.edit_message_text(info + "\n\nصفحه موردنظر رو انتخاب کن:", reply_markup=pages_keyboard(b_id, len(pages)))

        elif btype == "pdf":
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

        elif btype == "both":
            text_pages = await db.get_pages(b_id)
            files = await db.get_book_files(b_id)
            kb = []
            if text_pages:
                kb.append([InlineKeyboardButton("📱 نسخه متنی", callback_data=f"open_text_{b_id}")])
            if files:
                kb.append([InlineKeyboardButton("📄 نسخه PDF", callback_data=f"open_pdf_{b_id}")])
            if not kb:
                await query.edit_message_text("📭 محتوایی نیست.")
                return
            await query.edit_message_text(info + "\n\nکدوم نسخه؟", reply_markup=InlineKeyboardMarkup(kb))

        # بنر کتاب (اگه هست)
        if banner:
            await send_captured(context, user_id, banner)
        return

    # ═══════════ باز کردن نسخه متنی/PDF ═══════════
    if data.startswith("open_text_"):
        bid = int(data.split("_")[2])
        pages = await db.get_pages(bid)
        if not pages:
            await query.edit_message_text("📭 صفحه‌ای نیست.")
            return
        await query.edit_message_text(
            "📱 نسخه متنی\n\nصفحه موردنظر:",
            reply_markup=pages_keyboard(bid, len(pages))
        )
        return

    if data.startswith("open_pdf_"):
        bid = int(data.split("_")[2])
        files = await db.get_book_files(bid)
        if not files:
            await query.edit_message_text("📭 فایلی نیست.")
            return
        await query.edit_message_text("📄 نسخه PDF در حال ارسال...")
        for f in files:
            try:
                await context.bot.send_document(user_id, f[2], caption=f[1])
            except Exception:
                pass
        return

    # ═══════════ انتخاب صفحه ═══════════
    if data.startswith("pg_"):
        parts = data.split("_")
        bid = int(parts[1])
        page_num = int(parts[2])
        page = await db.get_page(bid, page_num)
        if not page:
            await query.answer("صفحه پیدا نشد.", show_alert=True)
            return
        page_id, content = page
        await context.bot.send_message(user_id, f"📄 صفحه {page_num}\n\n{content}")
        return

    # ═══════════ خرید از ادمین ═══════════
    if data.startswith("buy_"):
        bid = int(data.split("_")[1])
        book = await db.get_book(bid)
        if not book:
            await query.answer("کتاب پیدا نشد.", show_alert=True)
            return
        b_id, cat_id, title_fa, title_en, author, translator, desc, cover, btype, is_paid, price, preview, banner = book
        try:
            text = (
                f"🛒 درخواست خرید\n\n"
                f"👤 {query.from_user.first_name}\n"
                f"🆔 `{query.from_user.id}`\n"
                f"📛 @{query.from_user.username or 'ندارد'}\n\n"
                f"📖 کتاب: {title_fa}\n"
                f"💰 قیمت: {price or 'نامشخص'}"
            )
            await context.bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
            await query.edit_message_text("✅ درخواستت رسید دست ادمین.")
        except Exception:
            await query.edit_message_text(ERROR)
        return

    # ═══════════ ادمین: ساخت ژانر جدید ═══════════
    if not is_admin(user_id):
        return

    if data == "newcat":
        await db.set_fsm(user_id, "awaiting_cat_name")
        await query.edit_message_text("📝 اسم ژانر رو بفرست:")
        return

    if data == "newbook":
        cats = await db.get_all_categories()
        if not cats:
            await query.edit_message_text("❌ اول یه ژانر بساز.")
            return
        kb = []
        for c in cats:
            kb.append([InlineKeyboardButton(c[1], callback_data=f"selcat_{c[0]}")])
        await query.edit_message_text("📁 ژانر رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("selcat_"):
        cid = int(data.split("_")[1])
        await db.set_fsm(user_id, "awaiting_book_name_fa", {"category_id": cid})
        await query.edit_message_text("📖 اسم فارسی کتاب رو بفرست:")
        return

    # حذف ژانر
    if data.startswith("delcat_"):
        cid = int(data.split("_")[1])
        await db.delete_category(cid)
        await query.edit_message_text("✅ ژانر حذف شد.")
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

    # حذف کتاب
    if data.startswith("delbook_"):
        bid = int(data.split("_")[1])
        await db.delete_book(bid)
        await query.edit_message_text("✅ کتاب حذف شد.")
        return

    if data == "admin_list_books":
        books = await db.get_all_books()
        if not books:
            await query.edit_message_text("📭 کتابی نیست.")
            return
        text = "📚 کتاب‌ها:\n\n"
        for b in books:
            bid, cid, tfa, ten, btype, is_paid, price = b
            t = "💳" if is_paid else "🆓"
            text += f"#{bid} | {t} {tfa} ({btype})\n"
        await query.edit_message_text(text)
        return

    if data == "admin_del_book":
        books = await db.get_all_books()
        if not books:
            await query.edit_message_text("📭 کتابی نیست.")
            return
        kb = [[InlineKeyboardButton(f"🗑 {b[2]}", callback_data=f"delbook_{b[0]}")] for b in books]
        await query.edit_message_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
        return

    # حذف کانال
    if data.startswith("delch_"):
        cid = int(data.split("_")[1])
        await db.delete_channel(cid)
        await query.edit_message_text("✅ کانال حذف شد.")
        return

    # لینک یکبار مصرف
    if data == "otl_new":
        books = await db.get_all_books()
        if not books:
            await query.edit_message_text("📭 کتابی نیست.")
            return
        kb = [[InlineKeyboardButton(f"📖 {b[2]}", callback_data=f"otl_book_{b[0]}")] for b in books[:20]]
        await query.edit_message_text("کدوم کتاب؟", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("otl_book_"):
        bid = int(data.split("_")[2])
        await db.set_fsm(user_id, "otl_step1", {"book_id": bid})
        await query.edit_message_text(
            "⏰ مدت اعتبار (ساعت):\n"
            "مثال: `24` = ۲۴ ساعت\n"
            "`0` = بدون انقضا"
        )
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
            text += f"{s} #{lid} | `{code}` | کتاب #{bid}\n"
        await query.edit_message_text(text)
        return


# ═══════════ هندلر پیام ═══════════
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.message
    if not msg:
        return

    state, data = await db.get_fsm(user.id)

    # ═══════════ گروه ═══════════
    if msg.chat.type in ("group", "supergroup"):
        if msg.text:
            try:
                reply = get_ready_reply(msg.chat_id, msg.text)
                if reply:
                    await msg.reply_text(reply)
            except Exception as e:
                logger.error(f"[AUTO-REPLY] {e}")
        return

    # ═══════════ چت خصوصی ═══════════
    if not is_admin(user.id):
        if not await is_user_joined(context, user.id):
            await send_join_prompt(update, context)
            return

    # ═══════════ کاربر: کتاب‌ها ═══════════
    if msg.text == "📚 کتاب‌ها":
        cats = await db.get_all_categories()
        if not cats:
            await msg.reply_text("📭 هنوز ژانری اضافه نشده.")
            return
        kb = [[InlineKeyboardButton(f"📁 {c[1]}", callback_data=f"cat_{c[0]}")] for c in cats]
        await msg.reply_text("📚 ژانرها:\n\nیکی رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(kb))
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

    # ═══════════ FSM ادمین ═══════════
    if is_admin(user.id):

        # ─── reply_X ───
        if msg.text and msg.text.startswith("reply_"):
            try:
                msg_id = int(msg.text.replace("reply_", "").strip())
            except Exception:
                await msg.reply_text("❌ فرمت اشتباه. مثال: reply_5")
                return
            s_msg = await db.get_support_msg(msg_id)
            if not s_msg:
                await msg.reply_text("❌ پیام پیدا نشد.")
                return
            sid, uid, fname, txt = s_msg
            await db.set_fsm(user.id, "awaiting_reply_text", {"target": uid, "msg_id": msg_id})
            await msg.reply_text(f"✏️ جوابت به {fname} رو بنویس:\n\n💬 {txt[:50]}")
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

        # ─── پنل پیام‌ها ───
        if msg.text == "📩 پنل پیام‌ها":
            msgs = await db.get_all_support_msgs(30)
            if not msgs:
                await msg.reply_text("📭 پیامی نیست.")
                return
            text = f"📩 پیام‌ها ({len(msgs)})\n\n"
            for m in msgs[:15]:
                mid, uid, fname, txt, seen, created = m
                status = "✅" if seen else "🆕"
                text += f"{status} #{mid} | {fname}\n💬 {txt[:50]}\n\n"
            text += "برای جواب: `reply_شماره`"
            await msg.reply_text(text)
            return

        # ─── مدیریت ژانرها ───
        if msg.text == "📁 مدیریت ژانرها":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ افزودن ژانر", callback_data="newcat")],
                [InlineKeyboardButton("📋 لیست ژانرها", callback_data="admin_list_cats")],
                [InlineKeyboardButton("🗑 حذف ژانر", callback_data="admin_del_cat")],
            ])
            await msg.reply_text("📁 مدیریت ژانرها:", reply_markup=kb)
            return

        # ─── مدیریت کتاب‌ها ───
        if msg.text == "📚 مدیریت کتاب‌ها":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ افزودن کتاب", callback_data="newbook")],
                [InlineKeyboardButton("📋 لیست کتاب‌ها", callback_data="admin_list_books")],
                [InlineKeyboardButton("🗑 حذف کتاب", callback_data="admin_del_book")],
            ])
            await msg.reply_text("📚 مدیریت کتاب‌ها:", reply_markup=kb)
            return

        # ═══════════ FSM: افزودن ژانر ═══════════
        if state == "awaiting_cat_name":
            data["name"] = msg.text or ""
            await db.set_fsm(user.id, "awaiting_cat_desc", data)
            await msg.reply_text("📝 توضیحات ژانر (یا `skip`):")
            return

        if state == "awaiting_cat_desc":
            txt = msg.text or ""
            data["description"] = "" if txt.lower() == "skip" else txt
            await db.set_fsm(user.id, "awaiting_cat_banner", data)
            await msg.reply_text("🖼 بنر ژانر (یا `skip`):")
            return

        if state == "awaiting_cat_banner":
            if msg.text and msg.text.lower() == "skip":
                banner = None
            else:
                banner = capture_message(msg)
            cid = await db.add_category(data["name"], data.get("description", ""), banner)
            await db.clear_fsm(user.id)
            await msg.reply_text(f"✅ ژانر «{data['name']}» ساخته شد. (#{cid})")
            return

        # ═══════════ FSM: افزودن کتاب ═══════════
        if state == "awaiting_book_name_fa":
            data["title_fa"] = msg.text or ""
            await db.set_fsm(user.id, "awaiting_book_name_en", data)
            await msg.reply_text("📕 اسم انگلیسی (یا `skip`):")
            return

        if state == "awaiting_book_name_en":
            txt = msg.text or ""
            data["title_en"] = "" if txt.lower() == "skip" else txt
            await db.set_fsm(user.id, "awaiting_book_author", data)
            await msg.reply_text("✍️ اسم نویسنده (یا `skip`):")
            return

        if state == "awaiting_book_author":
            txt = msg.text or ""
            data["author"] = "" if txt.lower() == "skip" else txt
            await db.set_fsm(user.id, "awaiting_book_translator", data)
            await msg.reply_text("🖋 اسم مترجم (یا `skip`):")
            return

        if state == "awaiting_book_translator":
            txt = msg.text or ""
            data["translator"] = "" if txt.lower() == "skip" else txt
            await db.set_fsm(user.id, "awaiting_book_desc", data)
            await msg.reply_text("📝 توضیحات (یا `skip`):")
            return

        if state == "awaiting_book_desc":
            txt = msg.text or ""
            data["description"] = "" if txt.lower() == "skip" else txt
            await db.set_fsm(user.id, "awaiting_book_cover", data)
            await msg.reply_text("🖼 کاور کتاب (یا `skip`):")
            return

        if state == "awaiting_book_cover":
            if msg.text and msg.text.lower() == "skip":
                data["cover"] = None
            else:
                if msg.photo:
                    data["cover"] = msg.photo[-1].file_id
                else:
                    data["cover"] = None
            await db.set_fsm(user.id, "awaiting_book_type", data)
            await msg.reply_text(
                "📄 نوع کتاب:\n\n"
                "`متن` = رمان متنی (صفحه‌به‌صفحه)\n"
                "`PDF` = فایل PDF\n"
                "`هردو` = هم متن هم PDF"
            )
            return

        if state == "awaiting_book_type":
            txt = (msg.text or "").strip().lower()
            if txt == "متن":
                data["book_type"] = "text"
            elif txt == "pdf":
                data["book_type"] = "pdf"
            elif txt == "هردو":
                data["book_type"] = "both"
            else:
                await msg.reply_text("❌ بنویس: `متن` یا `PDF` یا `هردو`")
                return
            await db.set_fsm(user.id, "awaiting_book_paid", data)
            await msg.reply_text("💰 پولی هست؟ (`پولی` یا `رایگان`):")
            return

        if state == "awaiting_book_paid":
            txt = (msg.text or "").strip()
            if txt == "پولی":
                data["is_paid"] = 1
                await db.set_fsm(user.id, "awaiting_book_price", data)
                await msg.reply_text("💵 قیمت (مثلاً: ۵۰ هزار تومان):")
                return
            else:
                data["is_paid"] = 0
                data["price"] = ""
                await db.set_fsm(user.id, "awaiting_book_preview", data)
                await msg.reply_text("🔓 چند صفحه پیش‌نمایش رایگان؟ (یا `0`):")
                return

        if state == "awaiting_book_price":
            data["price"] = msg.text or ""
            await db.set_fsm(user.id, "awaiting_book_preview", data)
            await msg.reply_text("🔓 چند صفحه پیش‌نمایش رایگان؟ (یا `0`):")
            return

        if state == "awaiting_book_preview":
            try:
                data["preview"] = int(msg.text.strip())
            except Exception:
                data["preview"] = 0
            await db.set_fsm(user.id, "awaiting_book_banner", data)
            await msg.reply_text("🖼 بنر کتاب (یا `skip`):")
            return

        if state == "awaiting_book_banner":
            if msg.text and msg.text.lower() == "skip":
                data["banner"] = None
            else:
                data["banner"] = capture_message(msg)
            
            bid = await db.add_book(
                data["category_id"],
                data["title_fa"],
                data.get("title_en", ""),
                data.get("author", ""),
                data.get("translator", ""),
                data.get("description", ""),
                data.get("cover"),
                data.get("book_type", "pdf"),
                data.get("is_paid", 0),
                data.get("price", ""),
                data.get("preview", 0),
                data.get("banner")
            )
            data["book_id"] = bid

            btype = data.get("book_type")
            if btype == "text":
                await db.clear_fsm(user.id)
                await msg.reply_text(
                    f"✅ کتاب «{data['title_fa']}» ساخته شد. (#{bid})\n\n"
                    f"حالا از پنل → 📄 مدیریت صفحات → {data['title_fa']} → صفحات رو اضافه کن."
                )
            elif btype == "pdf":
                await db.set_fsm(user.id, "awaiting_pdf_file", data)
                await msg.reply_text("📄 فایل PDF رو بفرست:")
            elif btype == "both":
                await db.set_fsm(user.id, "awaiting_text_pages", data)
                await msg.reply_text("📱 اول صفحات متنی رو یکی‌یکی بفرست.\nوقتی تموم شد بنویس `done`.")
            return

        # ─── متن: صفحات ───
        if state == "awaiting_text_pages":
            if msg.text and msg.text.strip().lower() == "done":
                await db.set_fsm(user.id, "awaiting_pdf_file", data)
                await msg.reply_text("📄 حالا فایل PDF رو بفرست:")
                return
            if msg.text:
                bid = data["book_id"]
                pages = await db.get_pages(bid)
                next_num = len(pages) + 1
                await db.add_page(bid, next_num, msg.text)
                await msg.reply_text(f"✅ صفحه {next_num} ذخیره شد. صفحه بعدی یا `done`:")
            return

        # ─── PDF: فایل ───
        if state == "awaiting_pdf_file":
            file_id = None
            if msg.document:
                file_id = msg.document.file_id
            if file_id:
                bid = data["book_id"]
                await db.add_book_file(bid, "📄 PDF", file_id)
                await db.clear_fsm(user.id)
                await msg.reply_text(f"✅ کتاب کامل شد. (#{bid})")
            else:
                await msg.reply_text("❌ فایل PDF نفرستادی.")
            return

        # ═══════════ کانال ═══════════
        if msg.text == "➕ افزودن کانال":
            await db.set_fsm(user.id, "awaiting_channel")
            await msg.reply_text("📢 آیدی کانال:\nمثال: @mychannel")
            return

        if state == "awaiting_channel":
            try:
                chat = await context.bot.get_chat(msg.text.strip())
                invite = f"https://t.me/{chat.username}" if chat.username else chat.invite_link
                await db.add_channel(str(chat.id), "عضویت", invite)
                await msg.reply_text(f"✅ کانال اضافه شد.")
            except Exception as e:
                await msg.reply_text(f"❌ {e}")
            await db.clear_fsm(user.id)
            return

        if msg.text == "🗑 حذف کانال":
            channels = await db.get_all_channels()
            if not channels:
                await msg.reply_text("📭 کانالی نیست.")
                return
            kb = [[InlineKeyboardButton(f"🗑 {c[2]}", callback_data=f"delch_{c[0]}")] for c in channels]
            await msg.reply_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
            return

        if msg.text == "📋 مشاهده کانال‌ها":
            channels = await db.get_all_channels()
            if not channels:
                await msg.reply_text("📭 کانالی نیست.")
                return
            text = "📋 کانال‌ها:\n\n" + "\n".join(f"• `{c[1]}`" for c in channels)
            await msg.reply_text(text)
            return

        # ═══════════ بنر فوری ═══════════
        if msg.text == "📢 بنر فوری":
            await db.set_fsm(user.id, "awaiting_instant_banner")
            await msg.reply_text("📢 بنر فوری رو بفرست.\n\nبعد بنویس: `ارسال بنر فوری`")
            return

        if state == "awaiting_instant_banner":
            await db.set_instant_banner(capture_message(msg))
            await msg.reply_text("✅ تنظیم شد.\n\nبرای ارسال بنویس: `ارسال بنر فوری`")
            await db.clear_fsm(user.id)
            return

        if msg.text == "ارسال بنر فوری":
            count = await broadcast_instant_banner(context)
            await msg.reply_text(f"✅ ارسال شد به {count} کاربر." if count else "❌ بنری تنظیم نشده.")
            return

        # ═══════════ بنر زمان‌بندی ═══════════
        if msg.text == "⏰ بنر زمان‌بندی":
            await db.set_fsm(user.id, "awaiting_sched_banner_content")
            await msg.reply_text("⏰ بنر زمان‌بندی\n\nقدم ۱: محتوا رو بفرست.")
            return

        if state == "awaiting_sched_banner_content":
            data["message_json"] = capture_message(msg)
            await db.set_fsm(user.id, "awaiting_sched_banner_time", data)
            await msg.reply_text(
                "✅ محتوا ثبت شد.\n\n"
                "قدم ۲: زمان:\n"
                "میلادی: `2026-10-01 20:30`\n"
                "شمسی: `1404-07-15 20:30`"
            )
            return

        if state == "awaiting_sched_banner_time":
            run_at = parse_datetime(msg.text.strip())
            if not run_at:
                await msg.reply_text("❌ فرمت اشتباه.")
                return
            await db.add_scheduled_banner(data["message_json"], run_at)
            await db.clear_fsm(user.id)
            await msg.reply_text(f"✅ بنر زمان‌بندی شد!\n📅 {run_at[:16]}")
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
                f"📖 کتاب: #{bid}\n"
                f"⏰ اعتبار: {expire_text}\n\n"
                f"🔗 `{link}`"
            )
            return

        # ═══════════ آمار ═══════════
        if msg.text == "📊 آمار ربات":
            users = await db.get_users_count()
            cats = await db.get_all_categories()
            books = await db.get_all_books()
            channels = await db.get_all_channels()
            links = await db.get_all_onetime_links()
            support_count = await db.get_support_count()
            text = (
                f"📊 آمار ربات\n\n"
                f"👥 کاربران: {users}\n"
                f"📁 ژانرها: {len(cats)}\n"
                f"📚 کتاب‌ها: {len(books)}\n"
                f"📢 کانال‌ها: {len(channels)}\n"
                f"🔗 لینک‌ها: {len(links)}\n"
                f"📩 پیام‌ها: {support_count}"
            )
            await msg.reply_text(text)
            return

    # ═══════════ فایل معمولی ═══════════
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
