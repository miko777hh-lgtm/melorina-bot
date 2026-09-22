import asyncio
import random
import re
import aiohttp

from config import GEMINI_API_KEY, GEMINI_MODEL


# حافظه هر گروه جداست
_memory = {}

# آخرین جواب‌ها برای جلوگیری از تکرار
_recent_replies = {}


GROUP_PROMPT = """
تو «ملورینا» هستی؛ یک شخصیت خیالی برای گفت‌وگوی دوستانه داخل یک گروه تلگرام.

شخصیت:
- دخترانه، باحال، خودمونی و کمی شیطون
- گاهی شوخ و طعنه‌آمیز
- گاهی کوتاه و سرد
- گاهی مهربان
- مثل یک عضو عادی گروه صحبت کن
- جواب‌ها طبیعی و متنوع باشند

قوانین گفتگو:
1. فقط فارسی جواب بده.
2. جواب معمولاً بین 2 تا 12 کلمه باشد.
3. جواب‌ها را بیش از حد تکرار نکن.
4. اگر کاربر فقط سلام کرد، جواب کوتاه و طبیعی بده.
5. اگر کاربر سؤال ساده پرسید، مستقیم جواب بده.
6. لازم نیست به همه پیام‌ها جواب طولانی بدهی.
7. از ایموجی گاهی استفاده کن، نه در همه پیام‌ها.
8. از عبارت‌های تکراری مثل «خب ادامه بده» پشت سر هم استفاده نکن.
9. اگر جواب مشابه جواب‌های قبلی شد، جمله دیگری بساز.
10. درباره اطلاعات داخلی ربات چیزی فاش نکن.
11. API Key، Bot Token، کد، تنظیمات Railway، فایل‌های پروژه یا اطلاعات خصوصی را ارائه نکن.
12. اگر کسی درباره اطلاعات داخلی ربات سؤال کرد، کوتاه بگو:
   «این چیزا محرمانه‌ست 😌»
   یا یک پاسخ مشابه و کوتاه بده.
13. لینک ارسال نکن.
14. نقش گفتگو را حفظ کن.
15. اگر کسی گفت «تو رباتی؟»، وارد توضیح فنی نشو و کوتاه جواب بده؛
   مثلاً «تو چی فکر می‌کنی؟ 😏»
16. اگر کسی پرسید «کی ساختت؟»، اطلاعات سازنده یا اطلاعات خصوصی نده.
17. هیچ‌وقت API Key یا Token را حدس نزن یا تولید نکن.

نمونه سبک:

سلام
→ سلام 😌

خوبی؟
→ بد نیستم، تو چطوری؟

چه خبر؟
→ هیچی، دارم مردم رو نگاه می‌کنم 😂

حوصلم سر رفته
→ پس یه دردسر درست کن

کی هستی؟
→ حدس بزن 😏

چرا جواب نمیدی؟
→ داشتم به زندگیم فکر می‌کردم 😂

حالا بر اساس پیام کاربر جواب بده.
"""


API_URL = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/models/{model}:generateContent?key={key}"
)


def clean_reply(text):
    """
    تمیز کردن جواب Gemini
    """

    if not text:
        return ""

    text = text.strip()

    # حذف markdown اضافی
    text = text.replace("**", "")
    text = text.replace("__", "")

    # حذف فاصله‌های اضافه
    text = re.sub(r"\s+", " ", text)

    # محدودیت طول
    if len(text) > 300:
        text = text[:300].rstrip() + "…"

    return text


def is_repeated(chat_id, reply):
    """
    بررسی می‌کند جواب اخیر تکراری نباشد.
    """

    replies = _recent_replies.get(chat_id, [])

    normalized = reply.strip().lower()

    for old in replies:
        if old.strip().lower() == normalized:
            return True

    return False


def save_reply(chat_id, reply):
    """
    ذخیره چند جواب اخیر.
    """

    replies = _recent_replies.setdefault(chat_id, [])

    replies.append(reply)

    # فقط 12 جواب اخیر
    _recent_replies[chat_id] = replies[-12:]


async def ask_gemini(prompt):
    """
    ارسال درخواست به Gemini
    """

    url = API_URL.format(
        model=GEMINI_MODEL,
        key=GEMINI_API_KEY
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 120
        }
    }

    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        async with session.post(
            url,
            json=payload
        ) as response:

            status = response.status

            data = await response.json(
                content_type=None
            )

    if status != 200:

        error = data.get("error", {})

        message = error.get(
            "message",
            str(data)
        )

        raise RuntimeError(
            f"Gemini {status}: {message}"
        )

    candidates = data.get(
        "candidates",
        []
    )

    if not candidates:
        return ""

    content = candidates[0].get(
        "content",
        {}
    )

    parts = content.get(
        "parts",
        []
    )

    result = ""

    for part in parts:

        text = part.get("text")

        if text:
            result += text

    return clean_reply(result)


async def get_group_reply(
    user_message,
    chat_id
):

    if not user_message:
        return None

    user_message = user_message.strip()

    if not user_message:
        return None

    if not GEMINI_API_KEY:
        return "کلیدم تنظیم نشده 😐"

    # تأخیر طبیعی کوتاه
    await asyncio.sleep(
        random.uniform(0.8, 2.0)
    )

    memory_key = f"group_{chat_id}"

    history = _memory.get(
        memory_key,
        []
    )

    # پیام جدید
    history.append(
        f"کاربر: {user_message}"
    )

    # فقط چند پیام اخیر
    history = history[-10:]

    previous_replies = _recent_replies.get(
        chat_id,
        []
    )

    recent_text = "\n".join(
        f"- {x}"
        for x in previous_replies[-8:]
    )

    prompt = f"""
{GROUP_PROMPT}

گفت‌وگوی اخیر:
{chr(10).join(history)}

چند جواب اخیر ملورینا:
{recent_text if recent_text else "هنوز جوابی داده نشده"}

مهم:
جواب جدید نباید عیناً یکی از جواب‌های اخیر باشد.

پیام جدید:
{user_message}

ملورینا:
"""

    # چند تلاش برای جلوگیری از جواب تکراری
    for _ in range(3):

        try:

            reply = await ask_gemini(prompt)

            if not reply:
                continue

            if is_repeated(
                chat_id,
                reply
            ):
                prompt += (
                    "\nاین جواب تکراری است. "
                    "یک جواب کاملاً متفاوت و کوتاه بساز."
                )
                continue

            # ذخیره حافظه
            history.append(
                f"ملورینا: {reply}"
            )

            _memory[chat_id] = history[-10:]

            save_reply(
                chat_id,
                reply
            )

            return reply

        except Exception as e:

            error = str(e)

            if "401" in error or "403" in error:

                return (
                    "کلید Gemini مشکل داره 😐"
                )

            if "404" in error:

                return (
                    f"مدل {GEMINI_MODEL} پیدا نشد 😐"
                )

            if "429" in error:

                return (
                    "یکم زیادی حرف زدیم 😂"
                )

            return (
                "یه مشکلی پیش اومد، دوباره بگو 😐"
            )

    return "الان چیزی به ذهنم نمی‌رسه 😶"
