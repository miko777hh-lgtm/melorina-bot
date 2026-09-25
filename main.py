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
from banner import (
    send_file_banner, broadcast_instant_banner,
    capture_message, send_captured
)
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
        await send_file_to_user(context, user.id, result["file_id_db"])
        await send_file_banner(context, user.id)
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


# ═══════════ ارسال فایل ═══════════
async def send_file_to_user(context, chat_id, file_id_db):
    row = await db.get_file(file_id_db)
    if not row:
        return False
    file_id, ftype, caption = row
    try:
        if ftype == "photo":
            await context.bot.send_photo(chat_id, file_id, caption=caption)
        elif ftype == "video":
            await context.bot.send_video(chat_id, file_id, caption=caption)
        elif ftype == "audio":
            await context.bot.send_audio(chat_id, file_id, caption=caption)
        elif ftype == "voice":
            await context.bot.send_voice(chat_id, file_id, caption=caption)
        elif ftype == "animation":
            await context.bot.send_animation(chat_id, file_id, caption=caption)
        else:
            await context.bot.send_document(chat_id, file_id, caption=caption)
        return True
    except Exception:
        return False


# ═══════════ کیبورد دسته‌بندی صفحات (6 تا 6 تا) ═══════════
def pages_keyboard(book_id, total_pages):
    """صفحه‌بندی 6 تا 6 تا"""
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
        await query.edit_message_text(
            "📚 ژانرها:\n\nیکی رو انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if data.startswith("cat_"):
        cid = int(data.split("_")[1])
        books = await db.get_books_by_category(cid)
        if not books:
            await query.edit_message_text("📭 تو این ژانر کتابی نیست.")
            return
        kb = []
        for b in books:
            bid, name_fa, name_en, is_paid, price, ftype = b
            prefix = "💳" if is_paid else "🆓"
            kb.append([InlineKeyboardButton(f"{prefix} {name_fa}", callback_data=f"book_{bid}")])
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="user_categories")])
        await query.edit_message_text(
            "📚 کتاب‌ها:\n\nیکی رو انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if data.startswith("book_"):
        bid = int(data.split("_")[1])
        book = await db.get_book(bid)
        if not book:
            await query.edit_message_text(BOOK_NOT_FOUND)
            return

        b_id, cat_id, name_fa, name_en, desc, is_paid, price, banner, ftype, full_file = book

        # کتاب پولی → پیام به ادمین
        if is_paid == 1:
            text = (
                f"📖 {name_fa}\n"
                f"📕 {name_en or ''}\n\n"
                f"💳 این کتاب پولیه\n"
                f"💰 قیمت: {price or 'تماس با ادمین'}\n\n"
                f"برای خرید، به ادمین پیام بده."
            )
            kb = [[InlineKeyboardButton("📩 خرید از ادمین", callback_data=f"buy_{bid}")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
            return

        # کتاب رایگان
        if ftype == "full" and full_file:
            # کتاب کلی
            text = f"📖 {name_fa}\n📕 {name_en or ''}\n\n{desc or ''}"
            await query.edit_message_text(text)
            try:
                await context.bot.send_document(user_id, full_file, caption=name_fa)
                # بنر کتاب (اگه هست)
                if banner:
                    await send_captured(context, user_id, banner)
                else:
                    # بنر پای فایل عمومی
                    await send_file_banner(context, user_id)
            except Exception as e:
                await query.message.reply_text(f"❌ خطا: {e}")
            return

        if ftype == "pages":
            # کتاب صفحه‌به‌صفحه → کیبورد 6تا6
            pages = await db.get_pages(bid)
            if not pages:
                await query.edit_message_text("📭 هنوز صفحه‌ای اضافه نشده.")
                return
            text = f"📖 {name_fa}\n📕 {name_en or ''}\n\n{desc or ''}\n\nصفحه موردنظر رو انتخاب کن:"
            await query.edit_message_text(
                text,
                reply_markup=pages_keyboard(bid, len(pages))
            )
            return

        await query.edit_message_text("📭 محتوایی نیست.")
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
        page_id, file_id = page
        try:
            await context.bot.send_document(user_id, file_id, caption=f"صفحه {page_num}")
        except Exception:
            await context.bot.send_photo(user_id, file_id, caption=f"صفحه {page_num}")
        return

    # ═══════════ خرید از ادمین ═══════════
    if data.startswith("buy_"):
        bid = int(data.split("_")[1])
        book = await db.get_book(bid)
        if not book:
            await query.answer("کتاب پیدا نشد.", show_alert=True)
            return
        b_id, cat_id, name_fa, name_en, desc, is_paid, price, banner, ftype, full_file = book

        # پیام به ادمین
        try:
            text = (
                f"🛒 درخواست خرید\n\n"
                f"👤 {query.from_user.first_name}\n"
                f"🆔 `{query.from_user.id}`\n"
                f"📛 @{query.from_user.username or 'ندارد'}\n\n"
                f"📖 کتاب: {name_fa}\n"
                f"💰 قیمت: {price or 'نامشخص'}"
            )
            await context.bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
            await query.edit_message_text(
                "✅ درخواستت رسید دست ادمین.\nبه‌زودی جواب می‌گیری."
            )
        except Exception:
            await query.edit_message_text(ERROR)
        return

    # ═══════════ فقط ادمین ═══════════
    if not is_admin(user_id):
        return

    # ─── حذف فایل قدیمی ───
    if data.startswith("delfile_"):
        fid = int(data.split("_")[1])
        await db.delete_file(fid)
        await query.edit_message_text("✅ حذف شد.")
        return

    if data.startswith("editcap_"):
        fid = int(data.split("_")[1])
        await db.set_fsm(user_id, "awaiting_new_caption", {"file_id": fid})
        await query.edit_message_text("کپشن جدید رو بفرست:")
        return

    if data.startswith("delch_"):
        cid = int(data.split("_")[1])
        await db.delete_channel(cid)
        await query.edit_message_text("✅ حذف شد.")
        return

    # ─── حذف ژانر ───
    if data.startswith("delcat_"):
        cid = int(data.split("_")[1])
        await db.delete_category(cid)
        await query.edit_message_text("✅ ژانر حذف شد.")
        return

    # ─── حذف کتاب ───
    if data.startswith("delbook_"):
        bid = int(data.split("_")[1])
        await db.delete_book(bid)
        await query.edit_message_text("✅ کتاب حذف شد.")
        return

    # ─── لیست ژانرها (ادمین) ───
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

    # ─── لیست کتاب‌ها (ادمین) ───
    if data == "admin_list_books":
        books = await db.get_all_books()
        if not books:
            await query.edit_message_text("📭 کتابی نیست.")
            return
        text = "📚 کتاب‌ها:\n\n"
        for b in books:
            bid, cid, nfa, nen, desc, is_paid, price, ftype = b
            t = "💳" if is_paid else "🆓"
            text += f"#{bid} | {t} {nfa} ({ftype})\n"
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

    # ─── لینک یکبار مصرف ───
    if data == "otl_new":
        books = await db.get_all_books()
        if not books:
            await query.edit_message_text("📭 کتابی نیست.")
            return
        kb = []
        for b in books[:20]:
            bid, cid, nfa = b[0], b[1], b[2]
            kb.append([InlineKeyboardButton(f"📖 {nfa}", callback_data=f"otl_book_{bid}")])
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
        kb = []
        for c in cats:
            cid, cname, cdesc, cbanner = c
            kb.append([InlineKeyboardButton(f"📁 {cname}", callback_data=f"cat_{cid}")])
        await msg.reply_text(
            "📚 ژانرها:\n\nیکی رو انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
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
                    await msg.reply_text("✅ جواب فرستاده شد.")
                    if msg_id:
                        await db.mark_support_seen(msg_id)
                except Exception as e:
                    await msg.reply_text(f"❌ خطا: {e}")
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

        # ═══════════ مدیریت ژانرها ═══════════
        if msg.text == "📁 مدیریت ژانرها":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ افزودن ژانر", callback_data="newcat")],
                [InlineKeyboardButton("📋 لیست ژانرها", callback_data="admin_list_cats")],
                [InlineKeyboardButton("🗑 حذف ژانر", callback_data="admin_del_cat")],
            ])
            await msg.reply_text("📁 مدیریت ژانرها:", reply_markup=kb)
            return

        if msg.text == "➕ افزودن ژانر" or (msg.text and msg.text.startswith("افزودن ژانر")):
            pass  # از طریق callback میاد

        # ═══════════ مدیریت کتاب‌ها ═══════════
        if msg.text == "📚 مدیریت کتاب‌ها":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ افزودن کتاب", callback_data="newbook")],
                [InlineKeyboardButton("📋 لیست کتاب‌ها", callback_data="admin_list_books")],
                [InlineKeyboardButton("🗑 حذف کتاب", callback_data="admin_del_book")],
            ])
            await msg.reply_text("📚 مدیریت کتاب‌ها:", reply_markup=kb)
            return

        # ═══════════ مدیریت صفحات ═══════════
        if msg.text == "📄 مدیریت صفحات":
            books = await db.get_all_books()
            if not books:
                await msg.reply_text("📭 اول کتاب بساز.")
                return
            kb = []
            for b in books[:20]:
                bid, cid, nfa = b[0], b[1], b[2]
                kb.append([InlineKeyboardButton(f"📖 {nfa}", callback_data=f"manage_pages_{bid}")])
            await msg.reply_text("کتاب رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(kb))
            return

        # ═══════════ FSM: افزودن ژانر ═══════════
        if state == "awaiting_cat_name":
            data["name"] = msg.text or ""
            await db.set_fsm(user.id, "awaiting_cat_desc", data)
            await msg.reply_text("📝 توضیحات ژانر رو بفرست (یا بنویس `skip`):")
            return

        if state == "awaiting_cat_desc":
            txt = msg.text or ""
            data["description"] = "" if txt.lower() == "skip" else txt
            await db.set_fsm(user.id, "awaiting_cat_banner", data)
            await msg.reply_text("🖼 بنر ژانر رو بفرست (یا بنویس `skip`):")
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
        if state == "awaiting_book_cat":
            cats = await db.get_all_categories()
            if not cats:
                await msg.reply_text("❌ اول ژانر بساز.")
                await db.clear_fsm(user.id)
                return
            kb = []
            for c in cats:
                cid, cname, _, _ = c
                kb.append([InlineKeyboardButton(cname, callback_data=f"selcat_{cid}")])
            await msg.reply_text("ژانر رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(kb))
            return

        if state == "awaiting_book_name_fa":
            data["name_fa"] = msg.text or ""
            await db.set_fsm(user.id, "awaiting_book_name_en", data)
            await msg.reply_text("📕 اسم انگلیسی کتاب رو بفرست (یا `skip`):")
            return

        if state == "awaiting_book_name_en":
            txt = msg.text or ""
            data["name_en"] = "" if txt.lower() == "skip" else txt
            await db.set_fsm(user.id, "awaiting_book_desc", data)
            await msg.reply_text("📝 توضیحات کتاب رو بفرست (یا `skip`):")
            return

        if state == "awaiting_book_desc":
            txt = msg.text or ""
            data["description"] = "" if txt.lower() == "skip" else txt
            await db.set_fsm(user.id, "awaiting_book_paid", data)
            await msg.reply_text("💰 پولی هست؟ (بنویس `پولی` یا `رایگان`):")
            return

        if state == "awaiting_book_paid":
            txt = (msg.text or "").strip()
            if txt == "پولی":
                data["is_paid"] = 1
                await db.set_fsm(user.id, "awaiting_book_price", data)
                await msg.reply_text("💵 قیمت رو بفرست (مثلاً: ۵۰ هزار تومان):")
                return
            else:
                data["is_paid"] = 0
                data["price"] = ""
                await db.set_fsm(user.id, "awaiting_book_type", data)
                await msg.reply_text(
                    "📄 نوع کتاب:\n\n"
                    "`کلی` = همه صفحات تو یه فایل\n"
                    "`صفحه` = صفحه به صفحه"
                )
                return

        if state == "awaiting_book_price":
            data["price"] = msg.text or ""
            await db.set_fsm(user.id, "awaiting_book_type", data)
            await msg.reply_text(
                "📄 نوع کتاب:\n\n"
                "`کلی` = همه صفحات تو یه فایل\n"
                "`صفحه` = صفحه به صفحه"
            )
            return

        if state == "awaiting_book_type":
            txt = (msg.text or "").strip()
            if txt == "کلی":
                data["file_type"] = "full"
                await db.set_fsm(user.id, "awaiting_book_banner", data)
                await msg.reply_text("🖼 بنر کتاب رو بفرست (یا `skip`):")
            elif txt == "صفحه":
                data["file_type"] = "pages"
                await db.set_fsm(user.id, "awaiting_book_banner", data)
                await msg.reply_text("🖼 بنر کتاب رو بفرست (یا `skip`):")
            else:
                await msg.reply_text("❌ بنویس `کلی` یا `صفحه`")
            return

        if state == "awaiting_book_banner":
            if msg.text and msg.text.lower() == "skip":
                data["banner"] = None
            else:
                data["banner"] = capture_message(msg)
            
            # ساخت کتاب
            bid = await db.add_book(
                data["category_id"],
                data["name_fa"],
                data.get("name_en", ""),
                data.get("description", ""),
                data.get("is_paid", 0),
                data.get("price", ""),
                data.get("banner"),
                data.get("file_type", "full"),
                None
            )
            data["book_id"] = bid

            if data.get("file_type") == "full":
                await db.set_fsm(user.id, "awaiting_book_full_file", data)
                await msg.reply_text("📎 فایل کلی کتاب (PDF/ZIP/...) رو بفرست:")
            else:
                await db.clear_fsm(user.id)
                await msg.reply_text(
                    f"✅ کتاب «{data['name_fa']}» ساخته شد. (#{bid})\n\n"
                    f"حالا از پنل → 📄 مدیریت صفحات → {data['name_fa']} → صفحات رو اضافه کن."
                )
            return

        if state == "awaiting_book_full_file":
            file_id = None
            if msg.document:
                file_id = msg.document.file_id
            elif msg.photo:
                file_id = msg.photo[-1].file_id
            elif msg.video:
                file_id = msg.video.file_id
            if file_id:
                async with __import__("aiosqlite").connect(db.DB_PATH) as conn:
                    await conn.execute("UPDATE books SET full_file_id = ? WHERE id = ?", (file_id, data["book_id"]))
                    await conn.commit()
                await msg.reply_text(f"✅ فایل کلی ذخیره شد.\nکتاب #{data['book_id']} کامل شد.")
            else:
                await msg.reply_text("❌ فایلی نفرستادی.")
            await db.clear_fsm(user.id)
            return

        # ═══════════ افزودن صفحات ═══════════
        if state == "awaiting_pages_book":
            # این مرحله از callback میاد
            pass

        if state == "awaiting_page_file":
            bid = data.get("book_id")
            if not bid:
                await db.clear_fsm(user.id)
                return
            file_id = None
            if msg.document:
                file_id = msg.document.file_id
            elif msg.photo:
                file_id = msg.photo[-1].file_id
            if file_id:
                pages = await db.get_pages(bid)
                next_num = len(pages) + 1
                await db.add_page(bid, next_num, file_id)
                await msg.reply_text(
                    f"✅ صفحه {next_num} ذخیره شد.\n\n"
                    f"صفحه بعدی رو بفرست یا `done` بنویس."
                )
            else:
                await msg.reply_text("❌ فایل نفرستادی.")
            return

        if state == "awaiting_page_file" and msg.text and msg.text.lower() == "done":
            await db.clear_fsm(user.id)
            await msg.reply_text("✅ صفحات ذخیره شد.")
            return

        if msg.text and msg.text.lower() == "done" and state == "awaiting_page_file":
            await db.clear_fsm(user.id)
            await msg.reply_text("✅ تمام.")
            return

        # ═══════════ کانال ═══════════
        if msg.text == "➕ افزودن کانال":
            await db.set_fsm(user.id, "awaiting_channel")
            await msg.reply_text("📢 آیدی کانال رو بفرست:\nمثال: @mychannel")
            return

        if state == "awaiting_channel":
            try:
                chat = await context.bot.get_chat(msg.text.strip())
                invite = f"https://t.me/{chat.username}" if chat.username else chat.invite_link
                await db.add_channel(str(chat.id), chat.title, invite)
                await msg.reply_text(f"✅ {chat.title} اضافه شد.")
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
            text = "📋 کانال‌ها:\n\n" + "\n".join(f"• {c[2]} — `{c[1]}`" for c in channels)
            await msg.reply_text(text)
            return

        # ═══════════ بنر پای فایل ═══════════
        if msg.text == "🖼 بنر پای فایل":
            await db.set_fsm(user.id, "awaiting_file_banner")
            await msg.reply_text("🖼 بنر پای فایل رو بفرست (یا `skip`):")
            return

        if state == "awaiting_file_banner":
            if msg.text and msg.text.lower() == "skip":
                await msg.reply_text("لغو شد.")
            else:
                await db.set_file_banner(capture_message(msg))
                await msg.reply_text("✅ بنر پای فایل تنظیم شد.")
            await db.clear_fsm(user.id)
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
            await msg.reply_text(
                f"🔗 لینک‌ها ({len(links)}):",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            return

        if state == "otl_step1":
            try:
                hours = int(msg.text.strip())
            except Exception:
                await msg.reply_text("❌ عدد بفرست.")
                return
            bid = data.get("book_id")
            # لینک یکبار مصرف به کتاب وصل میشه
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
        await send_file_banner(context, msg.chat_id)
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
