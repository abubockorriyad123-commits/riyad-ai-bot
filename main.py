import json
import os
import logging
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
        return json.load(open(MEMORY_FILE))
    return {}

def save_memory(data):
    json.dump(data, open(MEMORY_FILE, "w"), indent=4)

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
# 🤖 GEMINI FUNCTION
# =====================
def ask_ai(prompt):
    response = model.generate_content(prompt)
    text = response.text

    # 🔐 Safety filter (identity lock)
    forbidden = ["gemini", "google", "openai", "api", "model"]
    for word in forbidden:
        if word in text.lower():
            text = "I am Riyad Assistant 😊"

    return text

# =====================
# 🚀 START
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Riyad Assistant 🤖",
        reply_markup=menu
    )

# =====================
# 💬 HANDLER
# =====================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id

    user = get_user(uid)
    name = user.get("name", "friend")

    # HELP
    if text == "ℹ️ Help":
        await update.message.reply_text("Use buttons to chat with Riyad Assistant 🤖")
        return

    # SET NAME MODE
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

    reply = ask_ai(prompt)

    await update.message.reply_text(reply)

# =====================
# 🚀 RUN BOT
# =====================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

print("Riyad Assistant is running...")
app.run_polling()
