import os
import logging
import asyncio
import threading
import sqlite3
import json
import google.generativeai as genai
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# =====================
# 🔑 CONFIG & LOGGING
# =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DB_NAME = "bot_memory.db"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# =====================
# 🗄️ SQLITE DATABASE SYSTEM
# =====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
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
        return json.loads(row[0])
    return []

def save_history(user_id, history):
    if len(history) > 12: # মেমোরি একটু বাড়িয়ে ১২টি করা হয়েছে
        history = history[-12:]
    
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO history (user_id, chat_history) VALUES (?, ?)",
                  (user_id, json.dumps(history)))
        conn.commit()

def clear_db_history(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM history WHERE user_id=?", (user_id,))
        conn.commit()

# =====================
# 🌐 RENDER PORT FIX
# =====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"AR Assistant is Running with Gemini & SQLite!")

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# =====================
# 🚀 GEMINI AI SETUP
# =====================
genai.configure(api_key=GEMINI_API_KEY)

# মডেল কনফিগারেশন
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction="You are AR Assistant. You are smart, intelligent, and friendly. Speak in Bengali and English. Never mention Google, Gemini, or being an AI model. Be helpful like a friend."
)

# =====================
# 🤖 AI FUNCTION WITH PERSISTENT MEMORY
# =====================
async def ask_gemini(user_id, user_text):
    try:
        history = get_history(user_id)
        
        # Gemini-র ফরম্যাটে হিস্ট্রি কনভার্ট করা
        formatted_history = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            formatted_history.append({"role": role, "parts": [msg["content"]]})

        # চ্যাট সেশন শুরু
        chat_session = model.start_chat(history=formatted_history)
        
        # রেসপন্স জেনারেট করা (Async wrapper ব্যবহার করে)
        response = await asyncio.to_thread(chat_session.send_message, user_text)
        reply = response.text
        
        # মেমোরি সেভ করা
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": reply})
        save_history(user_id, history)
        
        return reply
    except Exception as e:
        logging.error(f"Gemini Error: {e}")
        return "দুঃখিত বন্ধু, সার্ভারে একটু সমস্যা হচ্ছে। পরে আবার ট্রাই করো। 😅"

# =====================
# 🚀 TELEGRAM HANDLERS
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    clear_db_history(user_id)
    menu = ReplyKeyboardMarkup([["🤖 Chat", "ℹ️ Help"]], resize_keyboard=True)
    await update.message.reply_text(
        "👋 Hello! Ami AR Assistant.\nGemini AI power ekhon active! SQLite memory-r karone ami shob mone rakhte parbo. Bolo, kivabe shahajjo korte pari?", 
        reply_markup=menu
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.effective_user.id
    
    # টাইপিং স্ট্যাটাস দেখানো
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    reply = await ask_gemini(user_id, user_text)
    await update.message.reply_text(reply)

# =====================
# 🚀 MAIN RUNNER
# =====================
async def main():
    if not BOT_TOKEN or not GEMINI_API_KEY:
        print("BOT_TOKEN and GEMINI_API_KEY variables missing!")
        return
    
    init_db()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__ == '__main__':
    # হেলথ চেক থ্রেড শুরু
    threading.Thread(target=run_health_check, daemon=True).start()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
