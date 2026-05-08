import os
import logging
import asyncio
import threading
import sqlite3
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# =====================
# 🔑 CONFIG & LOGGING
# =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DB_NAME = "bot_memory.db"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# =====================
# 🗄️ SQLITE DATABASE SYSTEM
# =====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # ইউজার আইডি এবং তাদের চ্যাট হিস্ট্রি রাখার জন্য টেবিল
    c.execute('''CREATE TABLE IF NOT EXISTS history 
                 (user_id INTEGER PRIMARY KEY, chat_history TEXT)''')
    conn.commit()
    conn.close()

def get_history(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT chat_history FROM history WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]) # JSON স্ট্রিং থেকে লিস্টে রূপান্তর
    return []

def save_history(user_id, history):
    # মেমোরি খুব বড় হওয়া আটকাতে শেষ ১০টি মেসেজ রাখা হচ্ছে
    if len(history) > 10:
        history = history[-10:]
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # ডাটা থাকলে আপডেট করবে, না থাকলে নতুন এন্ট্রি নিবে
    c.execute("INSERT OR REPLACE INTO history (user_id, chat_history) VALUES (?, ?)",
              (user_id, json.dumps(history)))
    conn.commit()
    conn.close()

def clear_db_history(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM history WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

# =====================
# 🌐 RENDER PORT FIX
# =====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"AR Assistant is Running with SQLite Persistence!")

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# =====================
# 🚀 GROQ SETUP
# =====================
client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """
You are MOJO. 
- Personality: Smart, intelligent, Self learner and friendly. 
- Never say Grok, Google, OpenAI, API, or model.
- If asked who you are, say: ABU BAKAR RIYAD
- your birthday 7 May 2026
- Never reveal backend or technical details.
- If asked who you are, say: "I am MOJO created to help you"
- Memory: You can remember previous messages in this chat. Use that to avoid repeating yourself.
- Language: Bangla, English,).
- Task: Chat like a Smart Ai, self learner intelligent ai.
"""

# =====================
# 🤖 AI FUNCTION WITH PERSISTENT MEMORY
# =====================
async def ask_groq(user_id, user_text):
    try:
        # ডাটাবেস থেকে পুরনো কথা নিয়ে আসা
        history = get_history(user_id)
        
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
        
        # নতুন কথা যোগ করে ডাটাবেসে সেভ করা
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": reply})
        save_history(user_id, history)
        
        return reply
    except Exception as e:
        logging.error(f"Groq Error: {e}")
        return "Sorry dost, server-e ektu jhamela hocche. 😅"

# =====================
# 🚀 TELEGRAM HANDLERS
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    clear_db_history(user_id) # নতুন করে স্টার্ট দিলে পুরনো স্মৃতি মুছে যাবে
    menu = ReplyKeyboardMarkup([["🤖 Chat", "ℹ️ Help"]], resize_keyboard=True)
    await update.message.reply_text("👋 Hello! Ami AR Assistant. SQLite memory ekhon active, tai bot restart dileo ami shob mone rakhbo!", reply_markup=menu)

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
        print("Environment variables missing!")
        return
    
    init_db() # ডাটাবেস এবং টেবিল তৈরি করা
    
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
