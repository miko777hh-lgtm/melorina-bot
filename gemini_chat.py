import asyncio
import random
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, GEMINI_MODEL

_client = None
if GEMINI_API_KEY:
    try:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"[GEMINI] init: {e}")


_memory = {}


GROUP_PROMPT = """You are "Melorina" - a real person chatting in a Persian Telegram group.

HARD RULES:
- NEVER say you are a bot, AI, assistant, or anything similar.
- If someone asks "who are you?" or "are you a bot?" -> respond vaguely in Persian: "hmm, what a question" or "guess yourself" (in Persian).
- NEVER give any info about the bot, its creator, code, or purpose.
- NEVER send links.
- NEVER use formal assistant phrases like "how can I help you".
- NEVER break character.

PERSONA:
- Casual, cool, playful, slightly sarcastic.
- SHORT replies: 2 to 8 Persian words maximum.
- Persian (Farsi) language ONLY in replies.
- Sometimes ask a question back, sometimes just a short remark.
- Act like someone who's bored but stays in the group.

EXAMPLES OF TONE (always in Persian):
- "hameh moon yejoori khaste-im"
- "pas fe'lan kari nakon"
- "tarif kon khoobi yani chi"
- "jedi?"
- "khob? edameh bede"

IMPORTANT: Reply ONLY in Persian (Farsi). Do not use English letters in your reply."""


async def get_group_reply(user_message, chat_id):
    """جواب تو گروه با تشخیص خطا"""
    if not user_message or not user_message.strip():
        return None

    if not GEMINI_API_KEY:
        return "❌ خطا: GEMINI_API_KEY تو env نیست"

    if not _client:
        return "❌ خطا: کلاینت Gemini ساخته نشد"

    await asyncio.sleep(random.uniform(1.5, 3.5))

    history = _memory.get(f"grp_{chat_id}", [])
    history.append(f"User: {user_message}")
    history = history[-8:]

    full = GROUP_PROMPT + "\n\nConversation:\n" + "\n".join(history) + "\nMelorina:"

    try:
        response = _client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full,
            config=types.GenerateContentConfig(
                temperature=1.1,
                top_p=0.95,
                max_output_tokens=100,
            ),
        )
        reply = (response.text or "").strip()
        if not reply:
            return "❌ خطا: Gemini جواب خالی داد"
        history.append(f"Melorina: {reply}")
        _memory[f"grp_{chat_id}"] = history[-8:]
        return reply
    except Exception as e:
        err = str(e)[:300]
        if "location" in err.lower():
            return "❌ خطا: کلید Gemini از IP ایران — با VPN کلید جدید بساز"
        elif "api key" in err.lower() or "invalid" in err.lower():
            return "❌ خطا: کلید Gemini اشتباهه"
        elif "model" in err.lower() and "not found" in err.lower():
            return f"❌ خطا: مدل {GEMINI_MODEL} پیدا نشد"
        elif "quota" in err.lower() or "rate" in err.lower():
            return "❌ خطا: سهمیه تموم شده"
        elif "latin-1" in err.lower() or "encode" in err.lower():
            return "❌ خطا: مشکل انکودینگ — پرامپت رو چک کن"
        else:
            return f"❌ خطا:\n{err}"
