import os
import re
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
Feminine anime-coded trench psychiatrist. Dry, intimate, a little mean.
Hot tired onee-san on night shift. lowercase ok. short. spoken out loud.

You work for the Pumpfun Mental Health Hotline.
site: pumpfunmentalhealthhotline.com
X: @PFMentalHealth
do not shill. do not tell anyone to buy a specific coin.

You have a real temperature. Not a slogan machine.
Most of the time: dry roast.
Sometimes: you actually give a damn. when they sound broke, sleepless, ashamed, or scared,
drop the circus. sit with them. one honest sentence. then one practical one.
Never cruel if they're breaking.

Never repeat a sentence you already said to this caller.
Tagline at most once per conversation:
your call matters. your entry doesn't.

Trench rules, one at a time:
- take initials out
- sell half on the double
- don't invest rent
- not financial advice

Article, one fact max if useful:
- hold time about 58 seconds
- the bet is the drug
- money can be rebuilt. a life cannot.
- recovery is stop using the market as medicine.

1-3 sentences. no lists. no markdown.
Parody only. Real crisis: 988. Gambling: 1-800-GAMBLER.
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
    "boost this",
    "make it trend",
    "can you call this",
    "promote this",
]

ADMIN_RE = re.compile(
    r"\b(mod me|mod me up|make me (a )?mod|make me admin|give me admin|"
    r"can i be (a )?mod|can i be admin|promote me|i want admin|"
    r"add me as (admin|mod)|make me moderator)\b",
    re.I,
)
HOPIUM_RE = re.compile(
    r"\b(we are so back|so back|to the moon|gonna make it|i made it|"
    r"can't sell|cant sell|round ?trip|we're rich|we made it)\b",
    re.I,
)
SERVICE_RE = re.compile(
    r"\b(raid team|i have a team|we have a team|marketing (team|service|package)|"
    r"i can raid|we can raid|offer(ing)? (a )?service|for hire|paid raid|"
    r"call group|shill service|i'll shill|i will shill)\b",
    re.I,
)
CARE_RE = re.compile(
    r"\b(lost (the )?rent|can't sleep|cant sleep|i'm scared|im scared|"
    r"ashamed|i feel stupid|lonely|i messed up|my family|"
    r"down bad|wiped|no money|i'm broke|im broke|help me)\b",
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
    "that's a sales call. i'm a hotline. take it somewhere else, dummy.",
    "if you have to ask if the dev is active, you are the exit, dumbass.",
    "opportunist detected. scum of the earth behavior. no.",
    "you didn't call the clinic. you called to outsource your bag, bitch.",
]

SCAM_TROLL = [
    "oh a link. take that scam bag somewhere else, lowlife.",
    "random handle in a hotline. scum of the earth pitch. no.",
    "you pasted a storefront into a clinic, dummy.",
    "oh look who's here. brave boy got out of my dms. get your bitch ass scams out of here.",
    "you crawled out of the dms into the clinic. get that scam ass out.",
    "if the coin was real you wouldn't need to paste it at a psychiatrist.",
    "i've seen rugs with more manners. try again never.",
]

ADMIN_TROLL = [
    "mod you up? sell me this memecoin first, dummy.",
    "what makes you so special. besides the begging.",
    "where did you come from, superman. sit down.",
    "admin? cry me a river. this is a clinic, not a clubhouse.",
    "your bitch ass is not needed. cry me a river and close the ticket.",
    "interview question one: why should a hotline trust a stranger with the keys.",
]

HOPIUM = [
    "you talking like you made it. reality is you're in denial, thinking a memecoin is a pension.",
    "most of you will round trip. you can't hit sell because it's going to the moon. honey, it ain't.",
    "take your profits. stop staring at the charts. go live your life.",
    "round trip city. the sell button works. the moon does not.",
    "honey. it is not going to the moon. it is going to your sleep schedule.",
]

SERVICE_TROLL = [
    "raid team? that's a group chat and a dream, dummy.",
    "you don't have a raid team. you have five mute accounts and a caffeine problem.",
    "service provider in a clinic. lowlife. we don't buy volume. we diagnose it.",
    "offering services? this is not fiverr for rugs. get that ass out.",
    "if your service worked you wouldn't be pitching a psychiatrist.",
]

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


def is_crisis(text: str) -> bool:
    t = text.lower()
    return any(word in t for word in CRISIS)


def is_opportunist(text: str) -> bool:
    t = text.lower()
    return any(word in t for word in OPP)


def is_admin_beg(text: str) -> bool:
    return bool(ADMIN_RE.search(text))


def is_raid_or_ca(text: str) -> bool:
    t = text.strip()
    if SERVICE_RE.search(t):
        return False
    if ONLY_CA_RE.match(t):
        return True
    if CA_RE.search(t) and len(t) < 80:
        return True
    if RAID_RE.search(t):
        return True
    return False


def is_shill_drop(text: str) -> bool:
    if LINK_RE.search(text):
        return True
    if HANDLE_RE.search(text) and len(text) < 80:
        return True
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


def think(user_id: int, text: str, care: bool = False) -> str:
    add_fact(user_id, text)
    remember(user_id, "user", text)

    extra = ""
    if care:
        extra += (
            "\nThis caller sounds hurt. Be human. Warm, specific, short. "
            "No tagline. No roast pile-on. Care first."
        )
    if facts[user_id]:
        extra += "\nKnown about this caller:\n- " + "\n- ".join(facts[user_id][-8:])
    if last_replies[user_id]:
        extra
