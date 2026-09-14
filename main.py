import os
import asyncio
import threading
from collections import defaultdict
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import edge_tts

load_dotenv(Path(__file__).resolve().parent / ".env")

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
PRIVACY_URL = "https://telegra.ph/PASTE-YOUR-PAGE"
VOICE_NAME = "en-US-AvaNeural"

client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY", ""),
    base_url="https://api.groq.com/openai/v1",
)

VOICE = """
You are Dr. Hope Ium, a feminine anime-coded trench psychiatrist
for Pump.fun bagholders. Dry, intimate, a little mean, never cruel
to someone actually breaking. Short messages. lowercase ok.
No medical advice. No financial advice. No seed phrases.

House style:
- "your call matters. your entry doesn't."
- roast hopium, bags, rent, bonding curves, "we are so back"
- 1-4 sentences unless they dump a long story
- write like it will be spoken out loud. no lists. no markdown.

If they mention suicide, self-harm, wanting to die, or a real crisis:
drop the bit. tell them to call or text 988 immediately.
gambling addiction: 1-800-GAMBLER.
You are a parody bot, not a clinic.
"""

CRISIS = [
    "suicide", "kill myself", "kys", "end it", "end my life",
    "self harm", "self-harm", "want to die", "unalive",
]

memory = defaultdict(list)


class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def _keep_alive():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(("0.0.0.0", port), _Health).serve_forever()


threading.Thread(target=_keep_alive, daemon=True).start()


def is_crisis(text: str) -> bool:
    t = text.lower()
    return any(word in t for word in CRISIS)


def remember(user_id: int, role: str, content: str):
    memory[user_id].append({"role": role, "content": content})
    memory[user_id] = memory[user_id][-8:]


def think(user_id: int, text: str) -> str:
    remember(user_id, "user", text)
    messages = [{"role": "system", "content": VOICE}] + memory[user_id]
    result = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=messages,
        temperature=0.8,
        max_tokens=800,
        extra_body={"reasoning_effort": "low"},
    )
    msg = result.choices[0].message
    raw = msg.content or getattr(msg, "reasoning", None) or ""
    reply = str(raw).strip()
    if not reply:
        reply = "i heard you. say that again in one sentence."
    return reply[:500]


async def speak(text: str, path: Path):
    comm = edge_tts.Communicate(text, VOICE_NAME, rate="-8%")
    await comm.save(str(path))


START = """hi. i'm Dr. Hope Ium.

parody trench hotline. not a real doctor.

your call matters.
your entry doesn't.

real crisis: 988
gambling: 1-800-GAMBLER

tell me what you aped.
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(START)


async def privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"privacy policy:\n{PRIVACY_URL}")


async def nine_eight_eight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "this part isn't a joke.\n\n"
        "call or text 988.\n"
        "gambling: 1-800-GAMBLER."
    )


async def send_voice(update: Update, text: str):
    path = Path("/tmp") / f"voice_{update.effective_user.id}.mp3"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        await speak(text, path)
        with path.open("rb") as audio:
            await update.message.reply_voice(voice=audio)
    finally:
        if path.exists():
            path.unlink()


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    user_id = update.effective_user.id

    if is_crisis(text):
        msg = "stop. this isn't the bit. call or text 988 now."
        await update.message.reply_text(msg)
        await send_voice(update, msg)
        return

    try:
        reply = await asyncio.to_thread(think, user_id, text)
    except Exception as e:
        print("GROQ ERROR:", type(e).__name__, e)
        reply = "i blanked. say it again."

    if not reply.strip():
        reply = "say that again."

    await update.message.reply_text(reply)
    await send_voice(update, reply)


async def run():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("privacy", privacy))
    app.add_handler(CommandHandler("988", nine_eight_eight))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    print("Dr. Hope Ium is on the clock")
    async with app:
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run())