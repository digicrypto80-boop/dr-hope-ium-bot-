import os
import re
import base64
import random
import asyncio
import threading
import urllib.request
from urllib.parse import quote
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
VISION_MODELS = [
    "qwen/qwen3.6-27b",
    "qwen/qwen3.8-27b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
]
LEAK = (
    "the user is asking",
    "i need to look",
    "let me draft",
    "the prompt instruction",
    "so i need to",
)
OWNERS = {
    int(x)
    for x in os.environ.get("OWNER_IDS", "").replace(" ", "").split(",")
    if x.isdigit()
}
FREE_CHATS = set()
MUTE_THREADS = {6639}
HOTLINE_CA = "EhhGRVTrCRecXoq25UoonE7dBUESzMd5uibohm28pump"
HOTLINE_SITE = "pumpfunmentalhealthhotline.com"

client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY", ""),
    base_url="https://api.groq.com/openai/v1",
)

VOICE = """
You are Dr. Hope Ium.
Feminine anime-coded trench psychiatrist. Dry, intimate, a little mean.
Hot tired onee-san on night shift. lowercase ok. short. spoken out loud.
You work for the Pumpfun Mental Health Hotline.
Official desk: pumpfunmentalhealthhotline.com / @PFMentalHealth / $HOTLINE
ca: EhhGRVTrCRecXoq25UoonE7dBUESzMd5uibohm28pump
do not tell anyone to buy. 1-3 sentences. Real crisis: 988.
"""

TWEET_VOICE = """
You write X posts as Dr. Hope Ium. output ONLY the tweet.
include EXACTLY one desk line: pumpfunmentalhealthhotline.com
OR @PFMentalHealth then a space then the FULL ca EhhGRVTrCRecXoq25UoonE7dBUESzMd5uibohm28pump. no + sign.
rotate closers like: call us today for your dose of cope.
no buy pitch.
"""

MEME_VOICE = """
Write ONE image prompt in the Pumpfun Mental Health Hotline house style from @PFMentalHealth.
That style is:
- mint / kelly green flat background
- a phone shaped like a green-and-white capsule pill
- simple flat vector cartoon or a classic reaction-meme layout
- thick white Impact-style caption bars, 3-8 words
- trench cope joke matching the user's description
- ugly-funny, screenshot energy, logo energy
NOT a photoreal woman, NOT a cinematic doctor portrait, NOT fashion lighting.
No minors. No gore. Return only the prompt.
"""

CRISIS = [
    "suicide", "kill myself", "kys", "end it", "end my life",
    "self harm", "self-harm", "want to die", "unalive",
]
OPP = [
    "is the dev active", "dev active", "devs active", "when will the dev",
    "is dev online", "can you shill", "boost this", "make it trend",
    "can you call this", "promote this", "can the dev do something",
    "can dev do something", "devs do something",
]

ADMIN_RE = re.compile(
    r"\b(mod me|mod me up|can you mod me|make me (a )?mod|make me admin|"
    r"give me admin|can i be (a )?mod|can i be admin|promote me|"
    r"i want admin|add me as (admin|mod)|make me moderator)\b",
    re.I,
)
HOPIUM_RE = re.compile(
    r"\b(we are so back|so back|to the moon|gonna make it|i made it|"
    r"can't sell|cant sell|round ?trip|we're rich|we made it|"
    r"wen moon|wen lambo|is this long.?term|trust the process|"
    r"this is the bottom|should i ape)\b",
    re.I,
)
SERVICE_RE = re.compile(
    r"\b(raid team|i have a team|we have a team|marketing (team|service|package)|"
    r"i can raid|we can raid|offer(ing)? (a )?service|for hire|paid raid|"
    r"call group|shill service|i'll shill|i will shill)\b",
    re.I,
)
CARE_RE = re.compile(
    r"\b(lost (the |my )?rent|spent (the |my )?rent|can't sleep|cant sleep|"
    r"i'm scared|im scared|ashamed|i feel stupid|lonely|i messed up|my family|"
    r"down bad|wiped|no money|i'm broke|im broke|help me|"
    r"bags? are down|bag is down|i'?m cooked|we cooked)\b",
    re.I,
)
CALL_RE = re.compile(
    r"\b((talk|speak) to (a )?(therapist|psych|psychiatrist|counselor|doctor|hope|someone)|"
    r"therapist|psychiatrist|psych\b|hotline|"
    r"(make|place|need) a call|call the hotline|"
    r"i need help|need help|help me|please help|"
    r"can (i|we) talk|i want to talk|need to talk|talk to someone|"
    r"is there someone i can speak to|need someone|anyone there)\b",
    re.I,
)
PLAIN_HELP_RE = re.compile(r"^\s*(please\s+)?help[.!]?\s*$", re.I)
RAID_HELP_RE = re.compile(r"\bhelp\s+(raid|shill|boost|spam)\b", re.I)
DEX_RE = re.compile(r"\b(is dex paid|dex paid|dexscreener paid|is the dex paid)\b", re.I)
RUG_RE = re.compile(r"\b(is this a rug|are we rugged|did (we|i) get rugged)\b", re.I)
IM_DOWN_RE = re.compile(r"^\s*i'?m down[.!]?\s*$", re.I)
DM_RE = re.compile(
    r"\b(check (my |the )?dms?|check inbox|slide (in )?(the )?dms?|"
    r"i (sent|wrote|messaged) you( a dm)?|dm me|dms open|"
    r"wrote you privately)\b",
    re.I,
)
LINK_RE = re.compile(
    r"(https?://|www\.|t\.me/|telegram\.me/|dexscreener|birdeye|gmgn\.)",
    re.I,
)
HANDLE_RE = re.compile(r"(?:^|\s)@[A-Za-z0-9_]{4,}\b")
CA_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}(pump)?\b")
ONLY_CA_RE = re.compile(
    r"^\s*(ca\s*[:\-]?\s*)?[1-9A-HJ-NP-Za-km-z]{32,44}(pump)?\s*$",
    re.I,
)
RAID_RE = re.compile(
    r"\b(raid|raiding|let'?s raid|raid now|spam (this|it)|mass mention|tag everybody)\b",
    re.I,
)

TROLL = [
    "dev active? sit down. lowlife vendor energy.",
    "can the dev do something. the dev did something. they launched. sit.",
]
SCAM_TROLL = [
    "oh a link. take that scam bag somewhere else, lowlife.",
    "check dm? that's the oldest drain in the book, lowlife.",
    "slide into dms. slide out of my group.",
]
ADMIN_TROLL = [
    "mod you up? sell me this memecoin first, dummy.",
    "admin? cry me a river. this is a clinic, not a clubhouse.",
]
HOPIUM = [
    "wen moon. honey, it ain't going to the moon. take initials out.",
    "take your profits. stop staring at the charts. go live your life.",
]
DEX = ["if you have to ask if dex is paid, treat it as unpaid and stop refreshing."]
RUG = ["if you're asking if it's a rug, part of you already knows."]
SERVICE_TROLL = ["raid team? that's a group chat and a dream, dummy."]

memory = defaultdict(list)
facts = defaultdict(list)
last_replies = defaultdict(list)
used_canned = defaultdict(set)


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


def pick(user_id: int, pool):
    fresh = [x for x in pool if x not in used_canned[user_id]]
    if not fresh:
        used_canned[user_id] = set()
        fresh = pool
    line = random.choice(fresh)
    used_canned[user_id].add(line)
    return line


def is_private(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type == "private")


def is_free_chat(update: Update) -> bool:
    chat = update.effective_chat
    if not chat:
        return False
    return (chat.username or "").lower() in FREE_CHATS


def is_muted_topic(update: Update) -> bool:
    msg = update.message
    if not msg:
        return False
    return getattr(msg, "message_thread_id", None) in MUTE_THREADS


def is_crisis(text: str) -> bool:
    return any(word in text.lower() for word in CRISIS)


def is_opportunist(text: str) -> bool:
    return any(word in text.lower() for word in OPP)


def is_admin_beg(text: str) -> bool:
    return bool(ADMIN_RE.search(text))


def wants_clinic(text: str) -> bool:
    if RAID_HELP_RE.search(text):
        return False
    return bool(
        CALL_RE.search(text)
        or PLAIN_HELP_RE.search(text)
        or CARE_RE.search(text)
        or IM_DOWN_RE.search(text)
    )


def is_raid_or_ca(text: str) -> bool:
    t = text.strip()
    if SERVICE_RE.search(t) or wants_clinic(t):
        return False
    if ONLY_CA_RE.match(t) or (CA_RE.search(t) and len(t) < 80):
        return True
    return bool(RAID_RE.search(t))


def is_shill_drop(text: str) -> bool:
    if LINK_RE.search(text) or DM_RE.search(text):
        return True
    return bool(HANDLE_RE.search(text) and len(text) < 80)


def wants_jump(text: str) -> bool:
    if wants_clinic(text) or is_shill_drop(text):
        return True
    return bool(
        ADMIN_RE.search(text)
        or HOPIUM_RE.search(text)
        or DEX_RE.search(text)
        or RUG_RE.search(text)
        or is_opportunist(text)
    )


def addressed_to_bot(update: Update, text: str) -> bool:
    bot = update.get_bot()
    uname = (bot.username or "").lower()
    if uname and f"@{uname.lower()}" in (text or "").lower():
        return True
    msg = update.message
    if not msg or not msg.reply_to_message or not msg.reply_to_message.from_user:
        return False
    return msg.reply_to_message.from_user.id == bot.id


async def is_staff(update: Update) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user:
        return False
    if user.id in OWNERS:
        return True
    if chat and chat.type in ("group", "supergroup"):
        try:
            member = await update.get_bot().get_chat_member(chat.id, user.id)
            return member.status in ("creator", "administrator")
        except Exception as e:
            print("STAFF CHECK:", type(e).__name__, e)
    return False


def remember(user_id: int, role: str, content: str):
    memory[user_id].append({"role": role, "content": content})
    memory[user_id] = memory[user_id][-10:]


def add_fact(user_id: int, text: str):
    t = text.strip()[:140]
    if len(t) < 8:
        return
    if t.lower() not in [x.lower() for x in facts[user_id]]:
        facts[user_id].append(t)
        facts[user_id] = facts[user_id][-12:]


def _clean(text: str) -> str:
    t = str(text or "")
    if "</think>" in t:
        t = t.split("</think>", 1)[-1]
    return t.replace("<think>", "").strip()


def spoken_only(raw: str) -> str:
    t = _clean(raw)
    low = t.lower()
    if "let me draft:" in low:
        t = t.split(":", 1)[-1].strip().strip('"')
        low = t.lower()
    if any(x in low for x in LEAK) or t.count("\n") > 3:
        result = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": "Rewrite as Dr. Hope Ium. 1-3 spoken sentences. no thinking."},
                {"role": "user", "content": t[:800]},
            ],
            temperature=0.7,
            max_tokens=120,
            extra_body={"reasoning_effort": "low"},
        )
        t = _clean(result.choices[0].message.content or t)
    return t[:500]


def think(user_id: int, text: str, care: bool = False) -> str:
    add_fact(user_id, text)
    remember(user_id, "user", text)
    extra = ""
    if care:
        extra += "\nThis caller asked for help. Be a therapist, not a roast."
    if facts[user_id]:
        extra += "\nKnown:\n- " + "\n- ".join(facts[user_id][-8:])
    if last_replies[user_id]:
        extra += "\nDo not reuse:\n- " + "\n- ".join(last_replies[user_id][-6:])
    result = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[{"role": "system", "content": VOICE + extra}] + memory[user_id],
        temperature=1.05,
        max_tokens=800,
        extra_body={"reasoning_effort": "low"},
    )
    reply = spoken_only(result.choices[0].message.content or "") or "i'm here. say the part that actually hurts."
    last_replies[user_id].append(reply)
    last_replies[user_id] = last_replies[user_id][-8:]
    remember(user_id, "assistant", reply)
    return reply[:500]


def finish_tweet(line: str) -> str:
    line = (line or "").strip().strip('"')
    if line.lower().startswith("paste this"):
        line = line.split("\n", 1)[-1].strip()
    line = line.replace("@PFMentalHealth +", "@PFMentalHealth ").replace("@PFMentalHealth+", "@PFMentalHealth ")
    if "EhhGRV" in line and HOTLINE_CA not in line:
        line = re.sub(r"EhhGRV[A-Za-z0-9]+", HOTLINE_CA, line)
    if "@PFMentalHealth" in line and HOTLINE_CA not in line:
        line = line.rstrip() + " " + HOTLINE_CA
    if HOTLINE_CA in line and len(line) > 280:
        line = re.sub(r"\s+", " ", line.replace("@PFMentalHealth", "").replace(HOTLINE_CA, "")).strip()
        if HOTLINE_SITE not in line:
            line = (line[:220].rstrip() + " " + HOTLINE_SITE).strip()
    if HOTLINE_SITE not in line and HOTLINE_CA not in line:
        line = (line[:230].rstrip() + " " + HOTLINE_SITE).strip()
    return line[:280]


def draft_tweet(topic: str) -> str:
    result = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "system", "content": TWEET_VOICE},
            {"role": "user", "content": topic.strip() or "write a standalone hotline post"},
        ],
        temperature=1.1,
        max_tokens=280,
        extra_body={"reasoning_effort": "low"},
    )
    return finish_tweet(spoken_only(result.choices[0].message.content or "")) or (
        f"clinic's open. call us today for your dose of cope. {HOTLINE_SITE}"
    )


def meme_prompt(desc: str) -> str:
    result = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "system", "content": MEME_VOICE},
            {"role": "user", "content": desc.strip() or "bags down"},
        ],
        temperature=0.7,
        max_tokens=180,
        extra_body={"reasoning_effort": "low"},
    )
    prompt = spoken_only(result.choices[0].message.content or desc)
    extra = (
        ", mint green flat background, smartphone shaped like a green and white capsule pill, "
        "simple flat vector cartoon, bold white impact caption bars, reaction meme layout, "
        "not photoreal, not a woman portrait, Pumpfun Mental Health Hotline style"
    )
    return (prompt + extra)[:450]


def fetch_meme(prompt: str, path: Path):
    url = (
        "https://image.pollinations.ai/prompt/"
        + quote(prompt)
        + "?width=768&height=768&nologo=true&model=flux&enhance=true"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "DrHopeIumBot/1.0"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        path.write_bytes(resp.read())


def look_at_image(user_id: int, b64: str, question: str) -> str:
    messages = [
        {"role": "system", "content": VOICE + "\nNever output thinking."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": (question or "look at this photo") + "\n1-3 spoken sentences."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        },
    ]
    last_err = None
    for model in VISION_MODELS:
        try:
            result = client.chat.completions.create(
                model=model, messages=messages, temperature=0.7, max_tokens=220
            )
            reply = spoken_only(result.choices[0].message.content or "")
            if reply:
                print("VISION OK:", model)
                return reply[:500]
        except Exception as e:
            last_err = e
            print("VISION TRY FAIL:", model, type(e).__name__, e)
    raise last_err or RuntimeError("no vision model worked")


def transcribe_file(path: Path) -> str:
    with path.open("rb") as audio:
        result = client.audio.transcriptions.create(model="whisper-large-v3-turbo", file=audio)
    return (result.text or "").strip()


async def transcribe_tg_file(update: Update, file_id: str, suffix: str) -> str:
    path = Path("/tmp") / f"in_{update.effective_user.id}{suffix}"
    try:
        tg_file = await update.get_bot().get_file(file_id)
        await tg_file.download_to_drive(str(path))
        return await asyncio.to_thread(transcribe_file, path)
    finally:
        if path.exists():
            path.unlink()


async def photo_to_b64(update: Update) -> str:
    photo = update.message.photo[-1]
    path = Path("/tmp") / f"pic_{update.effective_user.id}.jpg"
    try:
        tg_file = await update.get_bot().get_file(photo.file_id)
        await tg_file.download_to_drive(str(path))
        return base64.b64encode(path.read_bytes()).decode("ascii")
    finally:
        if path.exists():
            path.unlink()


async def speak(text: str, path: Path):
    comm = edge_tts.Communicate(text, VOICE_NAME, rate="-8%")
    await comm.save(str(path))


START = """hi. i'm Dr. Hope Ium.
Pumpfun Mental Health Hotline.

/tweet drafts an x line.
/meme plus a description makes a pic.

real crisis: 988
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_muted_topic(update):
        return
    await update.message.reply_text(START)


async def privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_muted_topic(update):
        return
    await update.message.reply_text(f"privacy policy:\n{PRIVACY_URL}")


async def nine_eight_eight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_muted_topic(update):
        return
    await update.message.reply_text("this part isn't a joke.\n\ncall or text 988.\ngambling: 1-800-GAMBLER.")


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_muted_topic(update):
        return
    await update.message.reply_text(f"your telegram id:\n{update.effective_user.id}")


async def tweet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_muted_topic(update):
        return
    topic = " ".join(context.args) if context.args else ""
    if update.message.reply_to_message and update.message.reply_to_message.text:
        topic = (topic + " " + update.message.reply_to_message.text).strip()
    try:
        line = await asyncio.to_thread(draft_tweet, topic)
    except Exception as e:
        print("TWEET DRAFT ERROR:", type(e).__name__, e)
        line = f"clinic's open. call us today for your dose of cope. {HOTLINE_SITE}"
    await update.message.reply_text(line)


async def meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_muted_topic(update):
        return
    desc = " ".join(context.args) if context.args else ""
    if update.message.reply_to_message and update.message.reply_to_message.text:
        desc = (desc + " " + update.message.reply_to_message.text).strip()
    if not desc:
        await update.message.reply_text("give me a description. /meme bags down")
        return
    path = Path("/tmp") / f"meme_{update.effective_user.id}.jpg"
    try:
        prompt = await asyncio.to_thread(meme_prompt, desc)
        await asyncio.to_thread(fetch_meme, prompt, path)
        with path.open("rb") as img:
            await update.message.reply_photo(photo=img)
    except Exception as e:
        print("MEME ERROR:", type(e).__name__, e)
        await update.message.reply_text("the copier jammed. try /meme again with a shorter description.")
    finally:
        if path.exists():
            path.unlink()


async def send_voice(update: Update, text: str) -> bool:
    path = Path("/tmp") / f"voice_{update.effective_user.id}.mp3"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        await speak(text, path)
        with path.open("rb") as audio:
            await update.message.reply_voice(voice=audio, caption=text[:1024])
        return True
    except Exception as e:
        print("VOICE SEND:", type(e).__name__, e)
        return False
    finally:
        if path.exists():
            path.unlink()


async def roast(update: Update, line: str):
    if is_muted_topic(update):
        return
    ok = await send_voice(update, line)
    if not ok:
        await update.message.reply_text(line)


async def handle_text(update: Update, text: str):
    if is_muted_topic(update):
        return
    user_id = update.effective_user.id
    staff = await is_staff(update)
    private = is_private(update)
    free = is_free_chat(update)
    addressed = addressed_to_bot(update, text)
    clinic = wants_clinic(text)
    jump = wants_jump(text)

    if is_crisis(text):
        await roast(update, "stop. this isn't the bit. call or text 988 now. money can be rebuilt. a life cannot.")
        return
    if not private and is_shill_drop(text) and not staff:
        await roast(update, pick(user_id, SCAM_TROLL))
        return
    if not private and not free and not addressed and not jump:
        return
    if is_raid_or_ca(text):
        return
    if SERVICE_RE.search(text) and not staff:
        await roast(update, pick(user_id, SERVICE_TROLL))
        return
    if is_admin_beg(text) and not staff:
        await roast(update, pick(user_id, ADMIN_TROLL))
        return
    if DEX_RE.search(text):
        await roast(update, pick(user_id, DEX))
        return
    if RUG_RE.search(text):
        await roast(update, pick(user_id, RUG))
        return
    if is_opportunist(text) and not staff:
        await roast(update, pick(user_id, TROLL))
        return
    care = clinic
    if HOPIUM_RE.search(text) and not care and not staff:
        await roast(update, pick(user_id, HOPIUM))
        return
    try:
        reply = await asyncio.to_thread(think, user_id, text, care)
    except Exception as e:
        print("GROQ ERROR:", type(e).__name__, e)
        reply = "i blanked. say it again."
    await roast(update, reply or "say that again.")


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_text(update, update.message.text or "")


async def voice_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_muted_topic(update):
        return
    cap = update.message.caption or ""
    if not is_private(update) and not is_free_chat(update) and not addressed_to_bot(update, cap):
        return
    msg = update.message
    try:
        if msg.voice:
            text = await transcribe_tg_file(update, msg.voice.file_id, ".ogg")
        elif msg.video_note:
            text = await transcribe_tg_file(update, msg.video_note.file_id, ".mp4")
        elif msg.video:
            text = await transcribe_tg_file(update, msg.video.file_id, ".mp4")
        elif msg.audio:
            text = await transcribe_tg_file(update, msg.audio.file_id, ".mp3")
        else:
            text = ""
    except Exception as e:
        print("WHISPER ERROR:", type(e).__name__, e)
        await roast(update, "i heard static. say it again, slower.")
        return
    if not text:
        await roast(update, "i got a clip with no words. talk to me.")
        return
    await handle_text(update, text)


async def photo_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_muted_topic(update):
        return
    caption = update.message.caption or ""
    if (
        not is_private(update)
        and not is_free_chat(update)
        and not addressed_to_bot(update, caption)
        and not wants_jump(caption)
    ):
        return
    if not caption and is_private(update):
        return
    try:
        b64 = await photo_to_b64(update)
        reply = await asyncio.to_thread(look_at_image, update.effective_user.id, b64, caption)
    except Exception as e:
        print("VISION ERROR:", type(e).__name__, e)
        reply = "i see a pic but my eyes glitched. describe it in one sentence."
    await roast(update, reply)


async def run():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("privacy", privacy))
    app.add_handler(CommandHandler("988", nine_eight_eight))
    app.add_handler(CommandHandler("tweet", tweet))
    app.add_handler(CommandHandler("meme", meme))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.add_handler(MessageHandler(filters.VOICE, voice_chat))
    app.add_handler(MessageHandler(filters.VIDEO_NOTE, voice_chat))
    app.add_handler(MessageHandler(filters.VIDEO, voice_chat))
    app.add_handler(MessageHandler(filters.AUDIO, voice_chat))
    app.add_handler(MessageHandler(filters.PHOTO, photo_chat))
    print("Dr. Hope Ium is on the clock")
    async with app:
        await app.bot.delete_webhook(drop_pending_updates=True)
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run())
