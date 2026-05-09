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

from openai import OpenAI
from supabase import create_client, Client

# =====================
# CONFIG
# =====================

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

ADMIN_ID = 8287002826

logging.basicConfig(level=logging.INFO)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =====================
# MEMORY
# =====================

user_provider = {}
user_model = {}
user_step = {}

providers_cache = {}
models_cache = {}

SYSTEM_PROMPT = "You are AI assistant"

# =====================
# LOAD DATA
# =====================

def load_providers():
    global providers_cache
    res = supabase.table("providers").select("*").execute()
    providers_cache = {p["id"]: p for p in res.data}

def load_models():
    global models_cache
    res = supabase.table("ai_models").select("*").execute()

    models_cache = {}
    for m in res.data:
        models_cache.setdefault(m["provider_id"], []).append(m)

def load_prompt():
    global SYSTEM_PROMPT
    try:
        res = supabase.table("bot_config").select("system_prompt").eq("id", 1).execute()
        if res.data:
            SYSTEM_PROMPT = res.data[0]["system_prompt"]
    except:
        pass

def save_prompt(p):
    supabase.table("bot_config").upsert({
        "id": 1,
        "system_prompt": p
    }).execute()

# =====================
# AI CLIENT
# =====================

def get_client(pid):
    p = providers_cache.get(pid)
    if not p:
        return None

    return OpenAI(
        base_url=p["base_url"],
        api_key=p["api_key"]
    )

# =====================
# AI ENGINE
# =====================

async def ask_ai(uid, text):

    try:
        pid = user_provider.get(uid)
        mid = user_model.get(uid)

        provider = providers_cache.get(pid)
        model = None

        if pid in models_cache:
            for m in models_cache[pid]:
                if m["id"] == mid:
                    model = m

        if not provider or not model:
            return "❌ Provider/Model not selected"

        client = get_client(pid)

        loop = asyncio.get_event_loop()

        res = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=model["model_id"],
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ]
            )
        )

        return res.choices[0].message.content

    except Exception as e:
        logging.error(e)
        return "❌ Error"

# =====================
# ADMIN PANEL
# =====================

ADMIN_PANEL = [
    [InlineKeyboardButton("➕ Provider Wizard", callback_data="wiz_provider")],
    [InlineKeyboardButton("➕ Model Wizard", callback_data="wiz_model")],
    [InlineKeyboardButton("🧠 Edit Prompt", callback_data="wiz_prompt")],
]

BACK_BTN = InlineKeyboardMarkup(
    [[InlineKeyboardButton("⬅️ Back", callback_data="back")]]
)

# =====================
# START
# =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🤖 AI Platform Ready",
        reply_markup=ReplyKeyboardMarkup(
            [["⚙️ Admin Panel"]],
            resize_keyboard=True
        )
    )

# =====================
# ADMIN PANEL
# =====================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ No Access")

    await update.message.reply_text(
        "🛠 Admin Panel",
        reply_markup=InlineKeyboardMarkup(ADMIN_PANEL)
    )

# =====================
# WIZARD HANDLER
# =====================

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query
    await q.answer()

    uid = q.from_user.id

    if uid != ADMIN_ID:
        return

    # BACK
    if q.data == "back":
        user_step[uid] = None
        return await q.edit_message_text(
            "🔙 Admin Panel",
            reply_markup=InlineKeyboardMarkup(ADMIN_PANEL)
        )

    # =====================
    # PROVIDER WIZARD
    # =====================

    if q.data == "wiz_provider":
        user_step[uid] = "p_id"
        return await q.edit_message_text(
            "🧠 Step 1: Send Provider ID",
            reply_markup=BACK_BTN
        )

    # =====================
    # MODEL WIZARD
    # =====================

    if q.data == "wiz_model":
        user_step[uid] = "m_pid"
        return await q.edit_message_text(
            "🧠 Step 1: Provider ID",
            reply_markup=BACK_BTN
        )

    # =====================
    # PROMPT WIZARD
    # =====================

    if q.data == "wiz_prompt":
        user_step[uid] = "prompt"
        return await q.edit_message_text(
            "🧠 Send new system prompt",
            reply_markup=BACK_BTN
        )

# =====================
# MESSAGE HANDLER (WIZARD FLOW)
# =====================

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text
    uid = update.effective_user.id

    step = user_step.get(uid)

    # CANCEL SAFE
    if text and text.lower() in ["/cancel", "cancel", "back"]:
        user_step[uid] = None
        return await update.message.reply_text("🔙 Cancelled")

    # =====================
    # PROVIDER WIZARD FLOW
    # =====================

    if uid == ADMIN_ID and step:

        try:

            # STEP 1
            if step == "p_id":
                context.user_data["p_id"] = text
                user_step[uid] = "p_name"
                return await update.message.reply_text("Step 2: Provider Name")

            if step == "p_name":
                context.user_data["p_name"] = text
                user_step[uid] = "p_url"
                return await update.message.reply_text("Step 3: Base URL")

            if step == "p_url":
                context.user_data["p_url"] = text
                user_step[uid] = "p_key"
                return await update.message.reply_text("Step 4: API Key")

            if step == "p_key":

                supabase.table("providers").insert({
                    "id": context.user_data["p_id"],
                    "name": context.user_data["p_name"],
                    "base_url": context.user_data["p_url"],
                    "api_key": text
                }).execute()

                load_providers()
                user_step[uid] = None

                return await update.message.reply_text("✅ Provider Added")

            # =====================
            # MODEL WIZARD
            # =====================

            if step == "m_pid":
                context.user_data["m_pid"] = text
                user_step[uid] = "m_id"
                return await update.message.reply_text("Model ID")

            if step == "m_id":
                context.user_data["m_id"] = text
                user_step[uid] = "m_name"
                return await update.message.reply_text("Model Name")

            if step == "m_name":
                context.user_data["m_name"] = text
                user_step[uid] = "m_model"
                return await update.message.reply_text("Model API Name")

            if step == "m_model":

                supabase.table("ai_models").insert({
                    "provider_id": context.user_data["m_pid"],
                    "id": context.user_data["m_id"],
                    "model_name": context.user_data["m_name"],
                    "model_id": text
                }).execute()

                load_models()
                user_step[uid] = None

                return await update.message.reply_text("✅ Model Added")

            # =====================
            # PROMPT WIZARD
            # =====================

            if step == "prompt":

                global SYSTEM_PROMPT
                SYSTEM_PROMPT = text
                save_prompt(text)

                user_step[uid] = None

                return await update.message.reply_text("✅ Prompt Updated")

        except Exception as e:
            logging.error(e)
            user_step[uid] = None
            return await update.message.reply_text("❌ Error, reset")

    # =====================
    # NORMAL FLOW
    # =====================

    if text == "⚙️ Admin Panel":
        return await admin(update, context)

    await update.message.reply_text("🤖 Thinking...")

    reply = await ask_ai(uid, text)

    await update.message.reply_text(reply)

# =====================
# MAIN
# =====================

async def main():

    load_providers()
    load_models()
    load_prompt()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
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
