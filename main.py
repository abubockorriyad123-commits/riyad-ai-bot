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
# 🌐 RENDER PORT FIX (Web Service-এর জন্য)
# =====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Riyad Assistant is Running on Groq!")

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logging.info(f"Health check server started on port {port}")
    server.serve_forever()

# =====================
# 🚀 GROQ SETUP
# =====================
# Groq Client Initialize
client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """
You are Riyad Assistant. 
- Creator: Riyad.
- Language: Banglish (Mix of Bangla and English).
- Style: Friendly, short, and helpful.
- Rule: Never mention you are a model from Groq or Google.
"""

# =====================
# 🤖 AI FUNCTION
# =====================
async def ask_groq(user_text):
    try:
        loop = asyncio.get_event_loop()
        # Synchronous Groq call-কে Asynchronous করার জন্য run_in_executor ব্যবহার করা হয়েছে
        completion = await loop.run_in_executor(
            None, 
            lambda: client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_text}
                ],
                temperature=0.7,
                max_tokens=500
            )
        )
        return completion.choices[0].message.content
    except Exception as e:
        logging.error(f"Groq API Error: {e}")
        return "Sorry dost, server-e ektu jhamela hocche. Ektu por try koro! 😅"

# =====================
# 🚀 TELEGRAM HANDLERS
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = "👋 Hello! Ami Riyad Assistant.\nGroq API diye ekhon ami aro fast! Ki sahayyo korte pari?"
    menu = ReplyKeyboardMarkup([["🤖 Chat", "ℹ️ Help"]], resize_keyboard=True)
    await update.message.reply_text(welcome_text, reply_markup=menu)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    # "Typing..." স্ট্যাটাস দেখানোর জন্য
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # AI থেকে উত্তর নেওয়া
    ai_reply = await ask_groq(user_text)
    
    # উত্তর পাঠানো
    await update.message.reply_text(ai_reply)

# =====================
# 🚀 MAIN RUNNER
# =====================
async def main():
    if not BOT_TOKEN or not GROQ_API_KEY:
        logging.error("Environment Variables (BOT_TOKEN/GROQ_API_KEY) missing!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers যোগ করা
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Riyad Assistant (Groq) is starting...")

    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        # বটকে সচল রাখার জন্য
        await asyncio.Event().wait()

if __name__ == '__main__':
    # ১. Render-এর পোর্ট এরর দূর করতে আলাদা থ্রেডে সার্ভার চালানো
    threading.Thread(target=run_health_check, daemon=True).start()
    
    # ২. টেলিগ্রাম বট চালু করা
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot Stopped!")
