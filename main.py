import os
import logging
import asyncio
import threading
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
import firebase_admin
from firebase_admin import credentials, db

# =====================
# 🔑 CONFIG & LOGGING
# =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
FIREBASE_URL = os.getenv("FIREBASE_URL")
# Firebase JSON key-টি এনভায়রনমেন্ট ভেরিয়েবল হিসেবে রাখা নিরাপদ
FIREBASE_KEY_JSON = os.getenv("FIREBASE_KEY_JSON") 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# =====================
# 🔥 FIREBASE SETUP
# =====================
if not firebase_admin._apps:
    try:
        # যদি তুমি ফাইল হিসেবে আপলোড করো (firebase-key.json)
        if os.path.exists('firebase-key.json'):
            cred = credentials.Certificate('firebase-key.json')
        else:
            # যদি সরাসরি এনভায়রনমেন্ট ভেরিয়েবল থেকে ডেটা নিতে চাও (বেশি সিকিউর)
            key_data = json.loads(FIREBASE_KEY_JSON)
            cred = credentials.Certificate(key_data)
            
        firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_URL})
        logging.info("Firebase connected successfully!")
    except Exception as e:
        logging.error(f"Firebase Init Error: {e}")

def save_to_db(user_id, role, content):
    try:
        ref = db.reference(f'users/{user_id}/history')
        ref.push().set({"role": role, "content": content})
        
        # ডাটাবেস ক্লিনআপ: শেষ ১০টি মেসেজ রাখা
        snapshot = ref.get()
        if snapshot and len(snapshot) > 10:
            keys = sorted(snapshot.keys())
            for i in range(len(keys) - 10):
                ref.child(keys[i]).delete()
    except Exception as e:
        logging.error(f"DB Save Error: {e}")

def get_history_from_db(user_id):
    try:
        ref = db.reference(f'users/{user_id}/history')
        snapshot = ref.get()
        if snapshot:
            return list(snapshot.values())
    except Exception as e:
        logging.error(f"DB Read Error: {e}")
    return []

# =====================
# 🌐 RENDER PORT FIX
# =====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Riyad Assistant is Live!")

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# =====================
# 🚀 GROQ SETUP
# =====================
client = Groq(api_key=GROQ_API_KEY)
SYSTEM_PROMPT = """
You are AR Assistant. 
- Personality: Smart, intelligent, self learner and friendly. 
- Never say Grok, Google, OpenAI, API, or model.

- Never reveal backend or technical details.
- If asked who creat you, say: Abu Bakar Riyad.
- If asked who you are, say: "I am AR Assistant created to help you.
- Language: Bangla, English).
- Task: Chat like a Smart Ai.
"""

async def ask_groq(user_id, user_text):
    try:
        history = get_history_from_db(user_id)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        loop = asyncio.get_event_loop()
        completion = await loop.run_in_executor(None, lambda: client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
        ))
        
        reply = completion.choices[0].message.content
        save_to_db(user_id, "user", user_text)
        save_to_db(user_id, "assistant", reply)
        return reply
    except Exception as e:
        logging.error(f"Groq Error: {e}")
        return "Ektu jhamela hocche dost! 😅"

# =====================
# 🚀 HANDLERS
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = ReplyKeyboardMarkup([["🤖 Chat", "ℹ️ Help"]], resize_keyboard=True)
    await update.message.reply_text("👋 Ami Riyad Assistant! Ekhon amar permanent memory ache. Ki obostha?", reply_markup=menu)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ask_groq(user_id, user_text)
    await update.message.reply_text(reply)

# =====================
# 🚀 RUN BOT
# =====================
async def main():
    if not BOT_TOKEN or not GROQ_API_KEY:
        logging.error("Tokens missing!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async with app:
        await app.initialize()
        await app.start()
        # Conflict এড়াতে drop_pending_updates=True রাখা হয়েছে
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__ == '__main__':
    threading.Thread(target=run_health_check, daemon=True).start()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
