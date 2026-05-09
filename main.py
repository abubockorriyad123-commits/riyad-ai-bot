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
    filters,
    ContextTypes
)

from telegram.constants import ParseMode
from telegram.error import BadRequest

from openai import OpenAI
from supabase import create_client, Client

# =====================
# 🔑 CONFIG
# =====================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

ADMIN_ID = 8287002826

DEFAULT_MODEL = "inclusionai/ring-2.6-1t:free"

logging.basicConfig(level=logging.INFO)

# =====================
# 🧠 USER MODEL STORE
# =====================

user_model = {}

# =====================
# 🧠 MODEL MAP
# =====================

MODEL_MAP = {
    "model_ring": {
        "name": "🧠 AR Model 1 (Smart)",
        "model": "inclusionai/ring-2.6-1t:free"
    },

    "model_deepseek": {
        "name": "⚡ AR Model 2 (Fast)",
        "model": "baidu/cobuddy:free"
    },

    "model_llama": {
        "name": "🦙 AR Model 3 (Creative)",
        "model": "meta-llama/llama-3.3-70b-instruct:free"
    }
}

# =====================
# 🗄️ SUPABASE
# =====================

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

# =====================
# 🧠 DEFAULT PROMPT
# =====================

SYSTEM_PROMPT = """
You are MOJO, a high-intelligence AI assistant.
- Personality: Smart, intelligent, and friendly. 
- Never say Grok, Google, OpenAI, API, or model.
- Core Identity: MOJO AI.
- Creator: Developed by ABU BAKAR RIYAD (AR Technology Limited).
- Birthday: 7 May 2026.
- Language: Seamlessly switch between Bangla and English based on user input.
- Context Awareness: Always refer to past chat history and Supabase records for context-aware interactions.
"""

# =====================
# 🧠 PROMPT LOAD/SAVE
# =====================

def load_prompt():
    global SYSTEM_PROMPT

    try:
        res = supabase.table("bot_config") \
            .select("system_prompt") \
            .eq("id", 1) \
            .execute()

        if res.data:
            SYSTEM_PROMPT = res.data[0]["system_prompt"]

            logging.info("Prompt loaded from database")

    except Exception as e:
        logging.error(f"Prompt Load Error: {e}")


def save_prompt(prompt):
    try:
        supabase.table("bot_config").upsert({
            "id": 1,
            "system_prompt": prompt
        }).execute()

        logging.info("Prompt saved")

    except Exception as e:
        logging.error(f"Prompt Save Error: {e}")

# =====================
# 🗄️ CHAT HISTORY
# =====================

def get_history(user_id):
    try:
        res = supabase.table("history") \
            .select("chat_history") \
            .eq("user_id", str(user_id)) \
            .execute()

        if res.data:
            return json.loads(res.data[0]["chat_history"])

        return []

    except Exception as e:
        logging.error(f"History Get Error: {e}")
        return []


def save_history(user_id, history):

    try:

        if len(history) > 10:
            history = history[-10:]

        supabase.table("history").upsert({
            "user_id": str(user_id),
            "chat_history": json.dumps(history)
        }).execute()

    except Exception as e:
        logging.error(f"History Save Error: {e}")

# =====================
# 🌐 HEALTH CHECK
# =====================

class HealthCheckHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"MOJO AI Online")


def run_health():

    port = int(os.environ.get("PORT", 8080))

    HTTPServer(
        ("0.0.0.0", port),
        HealthCheckHandler
    ).serve_forever()

# =====================
# 🚀 OPENROUTER
# =====================

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,

    default_headers={
        "HTTP-Referer": "https://t.me",
        "X-Title": "MOJO AI"
    }
)

# =====================
# 💬 SAFE REPLY
# =====================

async def safe_reply(message, text, reply_markup=None):

    try:

        if not text:
            return

        await message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

    except BadRequest:

        await message.reply_text(
            text,
            reply_markup=reply_markup
        )

# =====================
# 🧠 AI FUNCTION
# =====================

async def ask_ai(user_id, user_text):

    try:

        history = get_history(user_id)

        model = user_model.get(
            user_id,
            DEFAULT_MODEL
        )

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]

        messages.extend(history)

        messages.append({
            "role": "user",
            "content": user_text
        })

        loop = asyncio.get_event_loop()

        res = await loop.run_in_executor(
            None,

            lambda: client.chat.completions.create(
                model=model,
                messages=messages
            )
        )

        reply = res.choices[0].message.content

        history.append({
            "role": "user",
            "content": user_text
        })

        history.append({
            "role": "assistant",
            "content": reply
        })

        save_history(user_id, history)

        return reply

    except Exception as e:

        logging.error(f"AI Error: {e}")

        return "দুঃখিত 😅 একটু সমস্যা হচ্ছে"

# =====================
# 🚀 START
# =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    menu = ReplyKeyboardMarkup(
        [
            [
                "👤 Creator Details",
                "🤖 Bot Info"
            ],

            [
                "⚙️ AI Model"
            ]
        ],

        resize_keyboard=True
    )

    await safe_reply(
        update.message,

        "✨ *MOJO AI Ready!*\n\n"
        "আমি তোমার AI বন্ধু 🤖",

        menu
    )

# =====================
# 🔘 MODEL UI
# =====================

async def model_ui(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [

        [
            InlineKeyboardButton(
                "🧠 AR Model 1",
                callback_data="model_ring"
            )
        ],

        [
            InlineKeyboardButton(
                "⚡ AR Model 2",
                callback_data="model_deepseek"
            )
        ],

        [
            InlineKeyboardButton(
                "🦙 AR Model 3",
                callback_data="model_llama"
            )
        ]
    ]

    await update.message.reply_text(
        "🤖 *Choose AI Model:*",

        reply_markup=InlineKeyboardMarkup(keyboard),

        parse_mode="Markdown"
    )

# =====================
# 🔁 BUTTON HANDLER
# =====================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    if query.data in MODEL_MAP:

        user_model[user_id] = MODEL_MAP[query.data]["model"]

        await query.edit_message_text(
            f"✅ Model Changed:\n"
            f"{MODEL_MAP[query.data]['name']}"
        )

# =====================
# 🔐 ADMIN COMMANDS
# =====================

async def set_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global SYSTEM_PROMPT

    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Access Denied"
        )
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/setprompt your prompt"
        )
        return

    new_prompt = " ".join(context.args)

    SYSTEM_PROMPT = new_prompt

    save_prompt(new_prompt)

    await update.message.reply_text(
        "✅ Prompt Updated Permanently"
    )


async def view_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Access Denied"
        )
        return

    await update.message.reply_text(
        f"🧠 Current Prompt:\n\n"
        f"{SYSTEM_PROMPT}"
    )

# =====================
# 💬 MESSAGE HANDLER
# =====================

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    user_id = update.effective_user.id

    # MODEL UI

    if text == "⚙️ AI Model":
        await model_ui(update, context)
        return

    # CREATOR

    if text == "👤 Creator Details":

        await safe_reply(
            update.message,
            "👤 Creator: Abu Bakar Riyad"
        )

        return

    # BOT INFO

    if text == "🤖 Bot Info":

        await safe_reply(
            update.message,
            "🤖 MOJO AI v2.0"
        )

        return

    # TYPING

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    # AI REPLY

    reply = await ask_ai(
        user_id,
        text
    )

    await safe_reply(
        update.message,
        reply
    )

# =====================
# 🚀 MAIN
# =====================

async def main():

    if not all([
        BOT_TOKEN,
        OPENROUTER_API_KEY,
        SUPABASE_URL,
        SUPABASE_KEY
    ]):

        print("Missing ENV")
        return

    # LOAD PROMPT

    load_prompt()

    app = ApplicationBuilder() \
        .token(BOT_TOKEN) \
        .build()

    # COMMANDS

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("setprompt", set_prompt)
    )

    app.add_handler(
        CommandHandler("viewprompt", view_prompt)
    )

    # CALLBACK

    app.add_handler(
        CallbackQueryHandler(button_handler)
    )

    # MESSAGES

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle
        )
    )

    async with app:

        await app.initialize()

        await app.start()

        await app.updater.start_polling()

        await asyncio.Event().wait()

# =====================
# 🚀 RUN
# =====================

if __name__ == "__main__":

    threading.Thread(
        target=run_health,
        daemon=True
    ).start()

    asyncio.run(main())
