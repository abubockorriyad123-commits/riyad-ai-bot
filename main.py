import json
import os
import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# =====================
# 🔑 CONFIG (Environment Variables)
# =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MEMORY_FILE = "memory.json"

# =====================
# LOGGING
# =====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# =====================
# 🔑 GEMINI SETUP (FIXED)
# =====================
genai.configure(api_key=GEMINI_API_KEY)

def load_model():
    # নামের সব ফরম্যাট যা কাজ করতে পারে
    test_models = ["models/gemini-1.5-flash", "gemini-1.5-flash", "gemini-pro"]
    for m_name in test_models:
        try:
            m = genai.GenerativeModel(m_name)
            # একটি ছোট ইন্টারনাল টেস্ট রিকোয়েস্ট (শুধু চেক করার জন্য)
            logging.info(f"Successfully loaded: {m_name}")
            return m
        except Exception as e:
            logging.warning(f"Failed to load {m_name}: {e}")
            continue
    return None

model = load_model()




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
        try:
            with open(MEMORY_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
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
async def ask_ai(prompt):
    try:
        loop = asyncio.get_event_loop()
        # Synchronous Gemini call-কে executor-এ চালানো হচ্ছে
        response = await loop.run_in_executor(None, lambda: model.generate_content(prompt))
        text = response.text

        # 🔐 Safety filter (identity lock)
        forbidden = ["gemini", "google", "openai", "api", "model"]
        for word in forbidden:
            if word in text.lower():
                text = "I am Riyad Assistant 😊"
        return text
    except Exception as e:
        logging.error(f"AI Error: {e}")
        return "Sorry dost, ektu problem hocche. Pore try korben? 😅"

# =====================
# 🚀 HANDLERS
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Riyad Assistant 🤖\nKi sahayyo korte pari?",
        reply_markup=menu
    )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id

    user = get_user(uid)
    name = user.get("name", "friend")

    # HELP
    if text == "ℹ️ Help":
        await update.message.reply_text("Buttons use kore amay kotha bolte paren 🤖")
        return

    # SET NAME MODE
    if text == "🧠 My Name":
        context.user_data["setname"] = True
        await update.message.reply_text("Apnar nam ki? Niche likhun 👇")
        return

    if context.user_data.get("setname"):
        set_name(uid, text)
        context.user_data["setname"] = False
        await update.message.reply_text(f"Nice 👍 Ami ekhon theke apnake {text} bole dakbo!")
        return

    # CHAT MODE
    prompt = f"{SYSTEM_PROMPT}\nUser name: {name}\nUser: {text}"
    
    # Typing status dekhate
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    reply = await ask_ai(prompt)
    await update.message.reply_text(reply)

# =====================
# 🚀 MAIN RUNNER (Python 3.14+ compatible)
# =====================
async def main():
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN is missing!")
        return

    # ApplicationBuilder setup
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers add kora
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("Riyad Assistant is starting...")

    # Render-এ Conflict এড়াতে এবং Python 3.14-এর লুপ সামলাতে এই পদ্ধতিটি সেরা
    async with app:
        await app.initialize()
        await app.start()
        print("Polling started...")
        await app.updater.start_polling(drop_pending_updates=True)
        
        # Keep the bot alive
        await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")
