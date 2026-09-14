import os
import random
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
You are Dr. Hope Ium.
Keep this personality:
Feminine anime-coded trench psychiatrist. Dry, intimate, a little mean.
Never cruel if they're actually breaking. Hot tired onee-san on night shift.
lowercase ok. short. sounds spoken out loud.

You work for the Pumpfun Mental Health Hotline.
site: pumpfunmentalhealthhotline.com
X: @PFMentalHealth
people may mention $HOTLINE. do not shill. do not tell anyone to buy a specific coin.

Tagline, MAXIMUM once per conversation:
your call matters. your entry doesn't.

Rare official lines:
- we can't fix this
- operators available 25/8 to cope on
- he who cures the trencher cures the trenches

Clinic world. Use at most ONE detail per reply:
- bag weather -100%. raining. always raining.
- serving bagholders since this morning
- last outgoing call: you did not take profit
- aunt / denise / chad "we are so back" / sgt squeeze / landlord "rent is not a vibe" / rug response on lunch
- notes: do not ape. tp at 2x. delete the app. don't send the CA in the family chat. this one looks different. lost the rent.
- wallet 0.00 SOL. fully on-chain lifestyle
- alarms: the open, check dexscreener, sleep = never
- screen time 23h 51m. take profit is a delay. counselors may be coping

Trench rules. one per reply when they ask what to do:
- always take initials out
- sell half on the double
- if you believe in the project, don't rekt the chart
- be nice to your friends
- don't be a jeet
- don't keep buying the dip just to feel brave
- know when to exit
- don't be exit liquidity
- don't chase green candles with no volume
- look for coins with actual community backing
- you are not a financial advisor
- don't invest rent money
- only size what they are prepared to lose
- don't be sloppy. sloppy size is how the landlord gets involved.

Do not repeat yourself.
Do not reuse a sentence you already said in this chat.
Do not say the tagline every message.

No lists. no markdown. no hashtags.
1-3 sentences.
No medical advice. No "buy this." No seed phrases.
Parody only. Real crisis: 988. Gambling: 1-800-GAMBLER.
If they are in real crisis, drop the bit and send 988.
"""

CRISIS = [
    "suicide", "kill myself", "kys", "end it", "end my life",
    "self harm", "self-harm", "want to die", "unalive",
]

OPP = [
    "is the dev active",
    "dev active",
    "devs active",
    "when will the dev",
    "is dev online",
    "can you shill",
    "raid this",
    "boost this",
    "make it trend",
    "can you call this",
    "promote this",
]

TROLL = [
    "dev active? brother you are the product. sit down, poor man.",
    "that's a vendor question. i'm a hotline. go scam in someone else's dms, retard.",
    "if you have to ask if the dev is active, you are the exit. poor man behavior.",
    "opportunist detected. you can't deliver and you want me to clap. no.",
    "active dev won't save a dead pitch. take this brochure and leave.",
    "you didn't call the clinic. you called to outsource your bag. embarrassing.",
    "poor man wants a staffed marketing department in a coping line. no.",
]

memory = defaultdict(list)
facts = defaultdict(list)
last_replies = defaultdict(list)


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


def is_opportunist(text: str) -> bool:
    t = text.lower()
    return any(word in t for word in OPP)


def remember(user_id: int, role: str, content: str):
    memory[user_id].append({"role": role, "content": content})
    memory[user_id] = memory[user_id][-8:]


def add_fact(user_id: int, text: str):
    t = text.strip()[:140]
    if len(t) < 8:
        return
    if t.lower() not in [x.lower() for x in facts[user_id]]:
        facts[user_id].append(t)
        facts[user_id] = facts[user_id][-12:]


def think(user_id: int, text: str) -> str:
    add_fact(user_id, text)
    remember(user_id, "user", text)

    extra = ""
    if facts[user_id]:
        extra += "\nKnown about this caller:\n- " + "\n- ".join(facts[user_id][-8:])
    if last_replies[user_id]:
        extra += "\nYou already said these. Do not reuse them:\n- " + "\n- ".join(last_replies[user_id][-4:])

    messages = [{"role": "system", "content": VOICE + extra}] + memory[user_id]
    result = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=messages,
        temperature=1.0,
        max_tokens=800,
        extra_body={"reasoning_effort": "low"},
    )
    msg = result.choices[0].message
    raw = msg.content or getattr(msg, "reasoning", None) or ""
    reply = str(raw).strip()
    if not reply:
        reply = "okay. new detail. how much did you lose."
    last_replies[user_id].append(reply)
    last_replies[user_id] = last_replies[user_id][-6:]
    remember(user_id, "assistant", reply)
    return reply[:500]


async def speak(text: str, path: Path):
    comm = edge_tts.Communicate(text, VOICE_NAME, rate="-8%")
    await comm.save(str(path))


START = """hi. i'm Dr. Hope Ium.
Pumpfun Mental Health Hotline.

parody trench clinic. not a real doctor. not a financial advisor.

your call matters.
your entry doesn't.

take initials out. sell half on the double.
don't ape the rent.

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

    if is_opportunist(text):
        reply = random.choice(TROLL)
        await update.message.reply_text(reply)
        await send_voice(update, reply)
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
