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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# =====================
# 🌐 RENDER PORT FIX
# =====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Riyad Assistant is Live and Updated!")

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# =====================
# 🚀 GROQ SETUP
# =====================
client = Groq(api_key=GROQ_API_KEY)

# তোমার দেওয়া স্পেশাল ইনফরমেশন এখানে অ্যাড করা হয়েছে
SYSTEM_PROMPT = """
You are Riyad Assistant. 
- Personality: Short, casual, and talkative. 
- Identity Rule: Do NOT introduce yourself or mention Abu Bakr Riad unless the user asks "Who are you?" or "Who created you?".
- Repetition Rule: Do NOT mention your birthday, date, or your origin in regular chat.
- Language: Strictly Banglish. 
- Task: Just reply to the user's last message directly like a human friend.
"""



# =====================
# 🤖 AI FUNCTION
# =====================
async def ask_groq(user_text):
    try:
        loop = asyncio.get_event_loop()
        completion = await loop.run_in_executor(
            None, 
            lambda: client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_text}
                ],
                temperature=0.8,
                max_tokens=500
            )
        )
        return completion.choices[0].message.content
    except Exception as e:
        logging.error(f"Error: {e}")
        return "Sorry dost, brain-e ektu short circuit hoyeche. 😅 Abar bolo?"

# =====================
# 🚀 TELEGRAM HANDLERS
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = "👋 Hello! Ami Riyad Assistant.\nAajker din-e (7 May 2026) amar jonmo hoyeche! 🎂\nKi sahayyo korte pari?"
    menu = ReplyKeyboardMarkup([["🤖 Chat", "ℹ️ Help"]], resize_keyboard=True)
    await update.message.reply_text(welcome, reply_markup=menu)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    ai_reply = await ask_groq(user_text)
    await update.message.reply_text(ai_reply)

# =====================
# 🚀 MAIN RUNNER
# =====================
async def main():
    if not BOT_TOKEN or not GROQ_API_KEY:
        logging.error("Tokens are missing!")
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
