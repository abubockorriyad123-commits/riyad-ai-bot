import os
import logging
import asyncio
import threading
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
from supabase import create_client, Client

# =====================
# 🔑 CONFIG & LOGGING
# =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# =====================
# 🗄️ SUPABASE DB SYSTEM
# =====================
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_history(user_id):
    try:
        response = supabase.table("history").select("chat_history").eq("user_id", user_id).execute()
        if response.data:
            return json.loads(response.data[0]['chat_history'])
        return []
    except Exception as e:
        logging.error(f"Supabase Get Error: {e}")
        return []

def save_history(user_id, history):
    if len(history) > 10:
        history = history[-10:] # শেষ ১০টি মেসেজ রাখা হচ্ছে
    
    try:
        data = {
            "user_id": user_id,
            "chat_history": json.dumps(history)
        }
        # ডাটা থাকলে আপডেট করবে, না থাকলে ইনসার্ট করবে
        supabase.table("history").upsert(data).execute()
    except Exception as e:
        logging.error(f"Supabase Save Error: {e}")

def clear_db_history(user_id):
    try:
        supabase.table("history").delete().eq("user_id", user_id).execute()
    except Exception as e:
        logging.error(f"Supabase Delete Error: {e}")

# =====================
# 🌐 RENDER HEALTH CHECK (Port Fix)
# =====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"MOJO AI is Online!")

def run_health_check():
    # Render অটোমেটিক $PORT এনভায়রনমেন্ট ভ্যারিয়েবল প্রদান করে
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logging.info(f"Health check server started on port {port}")
    server.serve_forever()

# =====================
# 🚀 GROQ AI SETUP
# =====================
client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """
You are MOJO. 
- Personality: Smart, intelligent, Self learner and friendly. 
- Identity: ABU BAKAR RIYAD.
- Birthday: 7 May 2026.
- Rules: Never mention specific AI models or APIs. Speak in Bangla or English.
- Use past chat history to provide context-aware answers.
"""

async def ask_groq(user_id, user_text):
    try:
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
        
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": reply})
        save_history(user_id, history)
        
        return reply
    except Exception as e:
        logging.error(f"Groq Error: {e}")
        return "Sorry dost, brain-e ektu pressure porchhe. Porer bar try kor! 😅"

# =====================
# 🤖 TELEGRAM HANDLERS
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    clear_db_history(user_id)
    menu = ReplyKeyboardMarkup([["🤖 Chat", "ℹ️ Help"]], resize_keyboard=True)
    await update.message.reply_text("✨ MOJO is Online! ✨", reply_markup=menu)

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
    if not all([BOT_TOKEN, GROQ_API_KEY, SUPABASE_URL, SUPABASE_KEY]):
        logging.critical("Missing Environment Variables!")
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
    # Health check server আলাদা থ্রেডে চালানো হচ্ছে Render-এর জন্য
    threading.Thread(target=run_health_check, daemon=True).start()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
