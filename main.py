# main.py
import os
import re
import json
import time
import uuid
import asyncio
from typing import List, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from langdetect import detect, DetectorFactory
import redis
import google.generativeai as genai

# deterministic langdetect
DetectorFactory.seed = 0

load_dotenv()

# ---------- Config ----------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")
MAX_CONTEXT = int(os.getenv("MAX_CONTEXT", "20"))

if not GEMINI_API_KEY:
    raise RuntimeError("Set GEMINI_API_KEY in .env")

genai.configure(api_key=GEMINI_API_KEY)
r = redis.from_url(REDIS_URL, decode_responses=True)

app = FastAPI(title="Ira Companion - Gemini FastAPI")

# make sure these directories exist
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ---------- Redis key helpers ----------
def user_chats_key(uid: str) -> str:
    return f"user:{uid}:chats"

def chat_history_key(uid: str, cid: str) -> str:
    return f"chat:{uid}:{cid}:history"

def user_lang_key(uid: str) -> str:
    return f"user:{uid}:lang"

# ---------- Utilities ----------
def detect_lang_safe(text: str) -> str:
    """Hybrid detection: langdetect + romanized Hindi keywords heuristic."""
    try:
        code = detect(text)
    except Exception:
        code = "en"
    hindi_keywords = {
        "kya", "kaise", "hai", "hain", "nahi", "haan", "tum", "mera", "tera",
        "kyu", "kyon", "batao", "pyaar", "yaar", "acha", "theek", "samjha", "kar",
        "kya", "kuch", "kal", "abhi", "chalo", "bolo"
    }
    words = re.findall(r"[a-zA-Z']+", text.lower())
    hindi_hits = sum(1 for w in words if w in hindi_keywords)
    eng_hits = sum(1 for w in words if w in {"i","you","the","is","are","love","good","ok","what","how","do"})
    # if langdetect says hi OR enough romanized hits -> hi
    if code.startswith("hi") or hindi_hits >= 2:
        return "hi"
    # mixed -> treat as Hinglish -> respond in Hindi style
    if hindi_hits and eng_hits:
        return "hi"
    return "en"

def create_chat_for_user(uid: str, title: str | None = None) -> str:
    cid = str(uuid.uuid4())[:8]
    chatlist = json.loads(r.get(user_chats_key(uid)) or "[]")
    title = title or f"Chat {len(chatlist) + 1}"
    chatlist.append({"chat_id": cid, "title": title, "created": time.time()})
    r.set(user_chats_key(uid), json.dumps(chatlist))
    return cid

def list_user_chats(uid: str) -> List[Dict[str, Any]]:
    return json.loads(r.get(user_chats_key(uid)) or "[]")

def append_message(uid: str, cid: str, role: str, content: str):
    key = chat_history_key(uid, cid)
    msg = {"role": role, "content": content, "ts": time.time()}
    r.rpush(key, json.dumps(msg))
    r.ltrim(key, -MAX_CONTEXT, -1)

def get_chat_history(uid: str, cid: str) -> List[Dict[str, Any]]:
    key = chat_history_key(uid, cid)
    items = r.lrange(key, 0, -1)  # oldest -> newest
    return [json.loads(x) for x in items]

# ---------- Frontend routes ----------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    uid = request.query_params.get("uid", "demo_user")
    chats = list_user_chats(uid)
    if not chats:
        create_chat_for_user(uid)
        chats = list_user_chats(uid)
    return templates.TemplateResponse("index.html", {"request": request, "chats": chats, "uid": uid})

@app.get("/chat/{cid}", response_class=HTMLResponse)
async def open_chat(request: Request, cid: str):
    uid = request.query_params.get("uid", "demo_user")
    chats = list_user_chats(uid)
    history = get_chat_history(uid, cid)
    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "chats": chats,
            "cid": cid,
            "uid": uid,
            "history": history,
        },
    )

# ---------- API endpoints ----------
@app.post("/api/new_chat")
async def api_new_chat(req: Request):
    data = await req.json()
    uid = data.get("uid", "demo_user")
    title = data.get("title")
    cid = create_chat_for_user(uid, title)
    return JSONResponse({"chat_id": cid})

@app.get("/api/chats")
async def api_chats(uid: str = "demo_user"):
    return list_user_chats(uid)

@app.post("/api/send")
async def api_send(request: Request):
    """
    Expects JSON: { "uid": "demo_user", "chat_id": "<cid>", "message": "..." }
    Streams chunks of assistant reply as plain text chunks.
    """
    data = await request.json()
    uid = data.get("uid", "demo_user")
    cid = data.get("chat_id")
    user_msg = data.get("message", "").strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="message required")
    if not cid:
        cid = create_chat_for_user(uid)

    append_message(uid, cid, "user", user_msg)

    # detect and persist user language
    detected = detect_lang_safe(user_msg)
    r.set(user_lang_key(uid), detected)

    # Build context lines
    history = get_chat_history(uid, cid)
    context_lines = []
    for m in history:
        role = m.get("role")
        content = m.get("content")
        context_lines.append(f"{role}: {content}")
    context_text = "\n".join(context_lines)

    user_lang = r.get(user_lang_key(uid)) or "en"

    prompt = (
        "You are Ira, a warm and affectionate companion. Follow these rules strictly:\n"
        "- Reply in 5 to 10 words only.\n"
        "- Keep responses incomplete (do not end with a final punctuation).\n"
        "- Tone: friendly, caring, sometimes romantic when appropriate; add emoji naturally.\n"
        "- Sound like a close friend and ask gentle follow-up questions when needed.\n"
        "- Mirror the user's language. The user's last language code: "
        f"{user_lang}\n"
        "- Avoid repeating earlier assistant replies.\n"
        "- Use the conversation context below.\n\n"
        f"Conversation:\n{context_text}\n\nUser: {user_msg}\nAssistant:"
    )

    # Call Gemini with streaming
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        stream = model.generate_content(prompt, stream=True)
    except Exception as e:
        fallback = "Sorry, thoda issue ho gaya, try again"
        append_message(uid, cid, "assistant", fallback)
        return StreamingResponse(iter([fallback]), media_type="text/plain")

    async def event_stream():
        collected = ""
        try:
            for chunk in stream:
                # chunk.text incremental
                if hasattr(chunk, "text") and chunk.text:
                    piece = chunk.text
                else:
                    piece = str(chunk)
                collected += piece
                # yield small chunk to client (client will render slowly)
                yield piece
                await asyncio.sleep(0)  # yield control (no delay here)
        except Exception as err:
            yield f"\n[Error: {err}]"
        finally:
            final = re.sub(r"\s+", " ", collected).strip()
            if final:
                append_message(uid, cid, "assistant", final)

    return StreamingResponse(event_stream(), media_type="text/plain")

# health
@app.get("/health")
async def health():
    return {"status": "ok"}