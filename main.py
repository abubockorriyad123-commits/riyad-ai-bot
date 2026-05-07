import os
import logging
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# =====================
# 🔑 CONFIG & LOGGING
# =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# =====================
# 🧠 MEMORY SYSTEM (Short-term)
# =====================
# প্রতিটা ইউজারের জন্য আলাদা আলাদা হিস্ট্রি সেভ থাকবে
user_histories = {}

def get_history(user_id):
    if user_id not in user_histories:
        user_histories[user_id] = []
    return user_histories[user_id]

def update_history(user_id, role, content):
    history = get_history(user_id)
    history.append({"role": role, "content": content})
    # শুধু শেষ ১০টি মেসেজ মনে রাখবে যাতে মেমোরি ফুল না হয়
    if len(history) > 10:
        history.pop(0)

# =====================
# 🌐 RENDER PORT FIX
# =====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Riyad Assistant is Running with Memory!")

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# =====================
# 🚀 GROQ SETUP
# =====================
client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """
You are Riyad Assistant. 
- Personality: Short, casual, and friendly. 
- Identity Rule: Do NOT introduce yourself or mention Abu Bakr Riad unless asked.
- Memory: You can remember previous messages in this chat. Use that to avoid repeating yourself.
- Language: Banglish (Mix of Bangla and English).
- Task: Chat naturally like a friend.
"""

# =====================
# 🤖 AI FUNCTION WITH MEMORY
# =====================
async def ask_groq(user_id, user_text):
    try:
        history = get_history(user_id)
        
        # মেসেজ লিস্ট তৈরি (System Prompt + History + Current Message)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        loop = asyncio.get_event_loop()
        completion = await loop.run_in_executor(
            None, 
            lambda: client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.7,
            )
        )
        
        reply = completion.choices[0].message.content
        
        # হিস্ট্রি আপডেট করা (ইউজার এবং এআই দুজনের কথাই সেভ হবে)
        update_history(user_id, "user", user_text)
        update_history(user_id, "assistant", reply)
        
        return reply
    except Exception as e:
        logging.error(f"Groq Error: {e}")
        return "Sorry dost, server-e ektu jhamela hocche. 😅"

# =====================
# 🚀 TELEGRAM HANDLERS
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_histories[user_id] = [] # স্টার্ট দিলে মেমোরি রিসেট হবে
    menu = ReplyKeyboardMarkup([["🤖 Chat", "ℹ️ Help"]], resize_keyboard=True)
    await update.message.reply_text("👋 Hello! Ami Riyad Assistant. Ekhon ami shob mone rakhte pari! Ki obostha?", reply_markup=menu)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.effective_user.id
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ask_groq(user_id, user_text)
    await update.message.reply_text(reply)

# =====================
# 🚀 MAIN RUNNER
# =====================
async def main():
    if not BOT_TOKEN or not GROQ_API_KEY:
        return
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__ == '__main__':
    threading.Thread(target=run_health_check, daemon=True).start()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
