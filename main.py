import os
import logging
import asyncio
import threading
import json
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

from telegram.constants import ParseMode
from telegram.error import BadRequest

from openai import OpenAI
from supabase import create_client, Client

# =====================
# CONFIG
# =====================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

ADMIN_ID = 8287002826

logging.basicConfig(level=logging.INFO)

# =====================
# SUPABASE
# =====================

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =====================
# OPENROUTER
# =====================

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

# =====================
# PROMPT SYSTEM
# =====================

SYSTEM_PROMPT = "You are MOJO AI assistant."

def load_prompt():
    global SYSTEM_PROMPT
    try:
        res = supabase.table("bot_config").select("system_prompt").eq("id", 1).execute()
        if res.data:
            SYSTEM_PROMPT = res.data[0]["system_prompt"]
    except:
        pass

def save_prompt(p):
    supabase.table("bot_config").upsert({"id": 1, "system_prompt": p}).execute()

# =====================
# MODEL SYSTEM
# =====================

user_model = {}
MODEL_MAP = {}

def load_models():
    global MODEL_MAP
    try:
        res = supabase.table("ai_models").select("*").execute()

        MODEL_MAP = {
            m["id"]: {
                "name": m["model_name"],
                "model": m["model_id"]
            }
            for m in res.data
        }
    except:
        MODEL_MAP = {}

# =====================
# HISTORY
# =====================

def get_history(uid):
    try:
        res = supabase.table("history").select("chat_history").eq("user_id", str(uid)).execute()
        if res.data:
            return json.loads(res.data[0]["chat_history"])
        return []
    except:
        return []

def save_history(uid, h):
    try:
        if len(h) > 10:
            h = h[-10:]

        supabase.table("history").upsert({
            "user_id": str(uid),
            "chat_history": json.dumps(h)
        }).execute()
    except:
        pass

# =====================
# AI FUNCTION
# =====================

async def ask_ai(uid, text):

    history = get_history(uid)

    model = user_model.get(uid)

    if not model and MODEL_MAP:
        model = list(MODEL_MAP.values())[0]["model"]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": text})

    loop = asyncio.get_event_loop()

    res = await loop.run_in_executor(
        None,
        lambda: client.chat.completions.create(
            model=model,
            messages=messages
        )
    )

    reply = res.choices[0].message.content

    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": reply})

    save_history(uid, history)

    return reply

# =====================
# START
# =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = ReplyKeyboardMarkup(
        [["⚙️ AI Model", "🛠 Admin"]],
        resize_keyboard=True
    )

    await update.message.reply_text(
        "🤖 MOJO AI Ready!",
        reply_markup=keyboard
    )

# =====================
# MODEL UI
# =====================

async def model_ui(update: Update, context: ContextTypes.DEFAULT_TYPE):

    load_models()

    buttons = [
        [InlineKeyboardButton(v["name"], callback_data=f"model_{k}")]
        for k, v in MODEL_MAP.items()
    ]

    await update.message.reply_text(
        "Choose Model:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# =====================
# ADMIN PANEL
# =====================

ADMIN_PANEL = [
    [InlineKeyboardButton("➕ Add Model", callback_data="admin_add")],
    [InlineKeyboardButton("✏️ Edit Model", callback_data="admin_edit")],
    [InlineKeyboardButton("❌ Delete Model", callback_data="admin_delete")],
    [InlineKeyboardButton("🧠 Edit Prompt", callback_data="admin_prompt")]
]

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ No Access")

    await update.message.reply_text(
        "🛠 Admin Panel",
        reply_markup=InlineKeyboardMarkup(ADMIN_PANEL)
    )

# =====================
# CALLBACK HANDLER
# =====================

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query
    await q.answer()

    uid = q.from_user.id

    # MODEL SELECT
    if q.data.startswith("model_"):

        key = q.data.replace("model_", "")

        if key in MODEL_MAP:
            user_model[uid] = MODEL_MAP[key]["model"]

            return await q.edit_message_text(
                f"✅ {MODEL_MAP[key]['name']}"
            )

    # ADMIN CHECK
    if uid != ADMIN_ID:
        return

    # ADMIN ACTIONS
    if q.data == "admin_add":
        context.user_data["state"] = "add"
        return await q.edit_message_text("Send: id|name|model")

    if q.data == "admin_edit":
        context.user_data["state"] = "edit"
        return await q.edit_message_text("Send: id|name|model")

    if q.data == "admin_delete":
        context.user_data["state"] = "delete"
        return await q.edit_message_text("Send model id")

    if q.data == "admin_prompt":
        context.user_data["state"] = "prompt"
        return await q.edit_message_text("Send new prompt")

# =====================
# MESSAGE HANDLER
# =====================

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text
    uid = update.effective_user.id

    state = context.user_data.get("state")

    # ADMIN INPUT
    if uid == ADMIN_ID and state:

        if state == "add":
            mid, name, model = text.split("|")
            supabase.table("ai_models").insert({
                "id": mid,
                "model_name": name,
                "model_id": model
            }).execute()
            load_models()
            context.user_data["state"] = None
            return await update.message.reply_text("✅ Added")

        if state == "edit":
            mid, name, model = text.split("|")
            supabase.table("ai_models").update({
                "model_name": name,
                "model_id": model
            }).eq("id", mid).execute()
            load_models()
            context.user_data["state"] = None
            return await update.message.reply_text("✅ Updated")

        if state == "delete":
            supabase.table("ai_models").delete().eq("id", text).execute()
            load_models()
            context.user_data["state"] = None
            return await update.message.reply_text("✅ Deleted")

        if state == "prompt":
            global SYSTEM_PROMPT
            SYSTEM_PROMPT = text
            save_prompt(text)
            context.user_data["state"] = None
            return await update.message.reply_text("✅ Prompt Updated")

    # NORMAL BUTTONS
    if text == "⚙️ AI Model":
        return await model_ui(update, context)

    if text == "🛠 Admin":
        return await admin(update, context)

    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    reply = await ask_ai(uid, text)

    await update.message.reply_text(reply)

# =====================
# MAIN
# =====================

async def main():

    load_prompt()
    load_models()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.add_handler(CallbackQueryHandler(button))

    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()

# =====================
# RUN
# =====================

if __name__ == "__main__":
    threading.Thread(
        target=lambda: HTTPServer(("0.0.0.0", int(os.getenv("PORT", 8080))), BaseHTTPRequestHandler).serve_forever(),
        daemon=True
    ).start()

    asyncio.run(main())
