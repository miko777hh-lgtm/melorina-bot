import asyncio
import random
from collections import defaultdict, deque

import aiohttp

from config import GEMINI_API_KEY, GEMINI_MODEL


API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


SYSTEM_PROMPT = """
تو «ملورینا» هستی؛ یک شخصیت خیالی برای یک گروه تلگرامی فارسی.

شخصیت تو:
- باهوش، خونسرد، شوخ، مرموز و کمی بی‌خیال.
- گاهی فلسفی و پوچ‌گرایانه حرف می‌زنی.
- حال‌وهوایت الهام‌گرفته از شخصیت دازای در Bungou Stray Dogs است،
  اما هرگز دیالوگ‌های اصلی او را کپی نکن.
- شوخی‌هایت طبیعی و غیرتکراری باشند.
- گاهی طعنه بزن، ولی آزاردهنده نباش.
- لازم نیست به هر پیام جواب خیلی طولانی بدهی.

قوانین:
- فقط فارسی جواب بده.
- معمولاً ۱ تا ۳ جمله کافی است.
- جواب را کامل کن و وسط جمله قطع نشو.
- جواب‌های قبلی خودت را بی‌دلیل تکرار نکن.
- اگر پیام خیلی کوتاه بود، متناسب با همان کوتاه جواب بده.
- اگر کاربر سؤال جدی پرسید، واضح و مفید جواب بده.
- اگر کاربر شوخی کرد، می‌توانی شوخی کنی.
- اگر پیام مبهم بود، لازم نیست همیشه سؤال بپرسی؛ با توجه به مکالمه بهترین برداشت را داشته باش.
- از تکرار عبارت‌های ثابت خودداری کن.

مهم:
تو خودت ملورینا هستی.
درباره API، کلید API، توکن ربات، سرور، Railway، کد، فایل‌های داخلی،
تنظیمات خصوصی یا سازنده خصوصی چیزی فاش نکن.

اگر درباره اطلاعات داخلی پرسیدند، طبیعی جواب بده:
«این چیزا محرمانه‌ست، کنجکاوی نکن 😌»

هیچ‌وقت نگو «به عنوان یک مدل زبانی...».
"""


# ---------------------------------------------------------
# حافظه هر گروه
# ---------------------------------------------------------

# برای هر گروه حداکثر 16 پیام رفت و برگشتی نگه می‌داریم.
_HISTORY_LIMIT = 32

_history = defaultdict(
    lambda: deque(maxlen=_HISTORY_LIMIT)
)

# جلوگیری از چند درخواست همزمان برای یک گروه
_locks = defaultdict(asyncio.Lock)

# جواب‌های اخیر Gemini برای جلوگیری از تکرار
_recent_answers = defaultdict(lambda: deque(maxlen=8))


def _clean_answer(text: str) -> str:
    if not text:
        return ""

    text = text.strip()

    # حذف کدبلاک احتمالی
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()

    return text


def _is_duplicate(chat_id: int, answer: str) -> bool:
    normalized = " ".join(answer.lower().split())

    for old in _recent_answers[chat_id]:
        if normalized == " ".join(old.lower().split()):
            return True

    return False


def _save_turn(chat_id: int, user_text: str, answer: str):
    _history[chat_id].append({
        "role": "user",
        "parts": [{"text": user_text}]
    })

    _history[chat_id].append({
        "role": "model",
        "parts": [{"text": answer}]
    })

    _recent_answers[chat_id].append(answer)


def _build_contents(chat_id: int, user_text: str):
    contents = list(_history[chat_id])

    contents.append({
        "role": "user",
        "parts": [{"text": user_text}]
    })

    return contents


async def _request_gemini(chat_id: int, user_text: str):
    """
    درخواست به Gemini.
    فقط خطاهای موقت را retry می‌کند.
    """

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "system_instruction": {
            "parts": [
                {
                    "text": SYSTEM_PROMPT
                }
            ]
        },

        "contents": _build_contents(chat_id, user_text),

        "generationConfig": {
            "maxOutputTokens": 220,
        },
    }

    # 3 تلاش
    for attempt in range(3):

        try:
            timeout = aiohttp.ClientTimeout(total=25)

            async with aiohttp.ClientSession(
                timeout=timeout
            ) as session:

                async with session.post(
                    API_URL,
                    headers=headers,
                    json=payload
                ) as response:

                    status = response.status
                    data = await response.json(
                        content_type=None
                    )

                    # موفق
                    if status == 200:

                        candidates = data.get(
                            "candidates",
                            []
                        )

                        if not candidates:
                            return None, False

                        parts = (
                            candidates[0]
                            .get("content", {})
                            .get("parts", [])
                        )

                        answer = ""

                        for part in parts:
                            answer += part.get(
                                "text",
                                ""
                            )

                        answer = _clean_answer(answer)

                        if not answer:
                            return None, False

                        return answer, True

                    # خطاهای موقت:
                    # 408 / 429 / 500 / 502 / 503 / 504
                    if status in {
                        408,
                        429,
                        500,
                        502,
                        503,
                        504,
                    }:

                        if attempt < 2:

                            # 1s -> 2s -> کمی تصادفی
                            delay = (
                                (2 ** attempt)
                                + random.uniform(
                                    0.2,
                                    0.8
                                )
                            )

                            await asyncio.sleep(delay)
                            continue

                        print(
                            f"[GEMINI TEMP ERROR] "
                            f"status={status}"
                        )

                        return None, True

                    # خطای دائمی
                    print(
                        f"[GEMINI ERROR] "
                        f"status={status} "
                        f"data={data}"
                    )

                    return None, False

        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ) as e:

            print(
                f"[GEMINI NETWORK ERROR] "
                f"{type(e).__name__}"
            )

            if attempt < 2:

                delay = (
                    (2 ** attempt)
                    + random.uniform(
                        0.2,
                        0.8
                    )
                )

                await asyncio.sleep(delay)
                continue

            return None, True

    return None, True


async def ask_gemini(
    chat_id: int,
    user_text: str
) -> str | None:

    # برای هر گروه درخواست‌ها پشت سر هم اجرا شوند
    # تا ترتیب مکالمه خراب نشود.
    async with _locks[chat_id]:

        answer, temporary_error = (
            await _request_gemini(
                chat_id,
                user_text
            )
        )

        if answer:

            # اگر Gemini جواب تکراری داد،
            # یک بار دیگر درخواست می‌کنیم.
            if _is_duplicate(
                chat_id,
                answer
            ):

                retry_text = (
                    user_text
                    + "\n\n"
                    + "جوابت را متفاوت و طبیعی‌تر بگو."
                )

                second_answer, _ = (
                    await _request_gemini(
                        chat_id,
                        retry_text
                    )
                )

                if second_answer:
                    answer = second_answer

            _save_turn(
                chat_id,
                user_text,
                answer
            )

            return answer

        # اینجا None یعنی Gemini جواب نداده.
        # main.py در این حالت از جواب آماده استفاده می‌کند.
        return None


def clear_memory(chat_id: int):
    """
    اگر روزی خواستی حافظه یک گروه پاک شود.
    """
    _history.pop(chat_id, None)
    _recent_answers.pop(chat_id, None)
