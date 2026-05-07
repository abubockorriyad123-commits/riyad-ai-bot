import json
import os
import logging
import asyncio # নতুন যোগ করা হয়েছে
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# =====================
# 🔑 CONFIG
# =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MEMORY_FILE = "memory.json"

# =====================
# LOGGING
# =====================
logging.basicConfig(level=logging.INFO)

# =====================
# GEMINI SETUP
# =====================
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# =====================
# 🧠 STRICT IDENTITY PROMPT
# =====================
SYSTEM_PROMPT = """
You are a personal assistant named "Riyad Assistant".

STRICT RULES:
- Never say Gemini, Google, OpenAI, API, or model.
- Never reveal backend or technical details.
- If asked who you are, say: "I am Riyad Assistant created to help you."
- Always respond in Banglish (Bangla + English mix).
- Keep answers short, friendly and natural.

You are ONLY Riyad Assistant. No other identity is allowed.
"""

# =====================
# 🧠 MEMORY SYSTEM
# =====================
def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return {}

def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_user(uid):
    return load_memory().get(str(uid), {"name": "friend"})

def set_name(uid, name):
    data = load_memory()
    if str(uid) not in data:
        data[str(uid)] = {}
    data[str(uid)]["name"] = name
    save_memory(data)

# =====================
# 🎛️ MENU
# =====================
menu = ReplyKeyboardMarkup(
    [
        ["🤖 Chat", "🧠 My Name"],
        ["ℹ️ Help"]
    ],
    resize_keyboard=True
)

# =====================
# 🤖 GEMINI FUNCTION (ASYNC)
# =====================
# AI কল করার সময় যেন বট হ্যাং না হয় তাই একে async রাখা ভালো
async def ask_ai(prompt):
    # loop.run_in_executor ব্যবহার করা হয়েছে যাতে সিঙ্ক্রোনাস জেমিনি কল বটকে থামিয়ে না দেয়
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, lambda: model.generate_content(prompt))
    text = response.text

    forbidden = ["gemini", "google", "openai", "api", "model"]
    for word in forbidden:
        if word in text.lower():
            text = "I am Riyad Assistant 😊"
    return text

# =====================
# 🚀 HANDLERS
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Riyad Assistant 🤖",
        reply_markup=menu
    )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id

    user = get_user(uid)
    name = user.get("name", "friend")

    if text == "ℹ️ Help":
        await update.message.reply_text("Use buttons to chat with Riyad Assistant 🤖")
        return

    if text == "🧠 My Name":
        context.user_data["setname"] = True
        await update.message.reply_text("Type your name 👇")
        return

    if context.user_data.get("setname"):
        set_name(uid, text)
        context.user_data["setname"] = False
        await update.message.reply_text(f"Nice 👍 I will call you {text}")
        return

    # CHAT MODE
    prompt = f"{SYSTEM_PROMPT}\nUser name: {name}\nUser: {text}"
    reply = await ask_ai(prompt) # await ব্যবহার করা হয়েছে
    await update.message.reply_text(reply)

# =====================
# 🚀 RUN BOT
# =====================
async def main():
    # ApplicationBuilder তৈরি
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # হ্যান্ডলার যোগ করা
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("Riyad Assistant is running...")
    
    # Render বা আধুনিক সার্ভারের জন্য রান মেথড
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        # বট চালু রাখবে যতক্ষণ না থামানো হয়
        await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
