import os
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from openai import AsyncOpenAI
from supabase import create_client, Client

# =====================
# CONFIG
# =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_ID = 8287002826

if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("❌ Missing ENV variables")

logging.basicConfig(level=logging.INFO)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =====================
# STATE
# =====================
user_provider = {}
user_model = {}
user_memory = {}
user_step = {}

providers_cache = {}
models_cache = {}

SYSTEM_PROMPT = "You are a helpful AI assistant"
MAX_MEMORY = 10

# =====================
# LOAD DATA FROM SUPABASE
# =====================
def load_providers():
    global providers_cache
    res = supabase.table("providers").select("*").execute()
    providers_cache = {p["id"]: p for p in (res.data or [])}

def load_models():
    global models_cache
    res = supabase.table("ai_models").select("*").execute()
    models_cache = {}
    for m in (res.data or []):
        models_cache.setdefault(m["provider_id"], []).append(m)

def load_prompt():
    global SYSTEM_PROMPT
    try:
        res = supabase.table("bot_config").select("system_prompt").eq("id", 1).execute()
        if res.data:
            SYSTEM_PROMPT = res.data[0]["system_prompt"]
    except:
        pass

# =====================
# AI ENGINE
# =====================
async def ask_ai(uid, text):
    try:
        pid = user_provider.get(uid)
        mid = user_model.get(uid)

        if not pid or not mid:
            return "❌ আগে /settings দিয়ে model select করো"

        provider = providers_cache.get(pid)
        model_info = next((m for m in models_cache.get(pid, []) if m["id"] == mid), None)

        if not provider or not model_info:
            return "❌ Model configuration error"

        client = AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=provider["api_key"]
        )

        if uid not in user_memory:
            user_memory[uid] = []

        user_memory[uid].append({"role": "user", "content": text})
        user_memory[uid] = user_memory[uid][-MAX_MEMORY:]

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ] + user_memory[uid]

        res = await client.chat.completions.create(
            model=model_info["model_id"],
            messages=messages
        )

        reply = res.choices[0].message.content

        user_memory[uid].append({"role": "assistant", "content": reply})
        user_memory[uid] = user_memory[uid][-MAX_MEMORY:]

        return reply

    except Exception as e:
        logging.error("AI ERROR", exc_info=True)
        return "❌ AI error"

# =====================
# COMMANDS
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 AI Bot Ready\nUse /settings",
        reply_markup=ReplyKeyboardMarkup([["⚙️ Admin Panel"]], resize_keyboard=True)
    )

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not providers_cache:
        return await update.message.reply_text("No providers found")

    buttons = [
        [InlineKeyboardButton(p["name"], callback_data=f"sel_p_{pid}")]
        for pid, p in providers_cache.items()
    ]

    await update.message.reply_text(
        "Select Provider:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    panel = [
        [InlineKeyboardButton("➕ Add Provider", callback_data="wiz_provider")],
        [InlineKeyboardButton("➕ Add Model", callback_data="wiz_model")]
    ]

    await update.message.reply_text("🛠 Admin Panel", reply_markup=InlineKeyboardMarkup(panel))

# =====================
# CALLBACK HANDLER
# =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    # Provider select
    if q.data.startswith("sel_p_"):
        pid = q.data.replace("sel_p_", "")
        user_provider[uid] = pid

        models = models_cache.get(pid, [])

        buttons = [
            [InlineKeyboardButton(m["model_name"], callback_data=f"sel_m_{m['id']}")]
            for m in models
        ]

        await q.edit_message_text(
            "Select Model:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    # Model select
    elif q.data.startswith("sel_m_"):
        mid = q.data.replace("sel_m_", "")
        user_model[uid] = mid

        await q.edit_message_text("✅ Setup Complete")

    else:
        await q.edit_message_text("❌ Unknown action")

# =====================
# MESSAGE HANDLER
# =====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    if text == "⚙️ Admin Panel":
        return await admin(update, context)

    msg = await update.message.reply_text("🤔 Thinking...")
    reply = await ask_ai(uid, text)
    await msg.edit_text(reply)

# =====================
# HEALTH SERVER
# =====================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

# =====================
# MAIN (NO CRASH VERSION)
# =====================
def main():
    load_providers()
    load_models()
    load_prompt()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Render health server
    threading.Thread(
        target=lambda: HTTPServer(
            ("0.0.0.0", int(os.getenv("PORT", 8080)))
        ).serve_forever(),
        daemon=True
    ).start()

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
