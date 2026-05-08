import os
import logging
import asyncio
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, ReplyKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from groq import Groq

# =========================
# 🔑 CONFIG & LOGGING
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

user_histories = {}

def update_history(user_id, role, content):
    if user_id not in user_histories:
        user_histories[user_id] = []
    user_histories[user_id].append({"role": role, "content": content})
    if len(user_histories[user_id]) > 20: # ২০টা মেসেজ মেমোরিতে থাকবে
        user_histories[user_id] = user_histories[user_id][-20:]

# =========================
# 🌐 RENDER HEALTH CHECK
# =========================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"AR Assistant Running Successfully!")

    def log_message(self, format, *args): return

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# =========================
# 🎨 IMAGE GEN (FREE)
# =========================
async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("❌ Prompt দিতে হবে। যেমন: `/img flying car`", parse_mode="Markdown")
        return

    await update.message.reply_text("🎨 তোমার ছবি তৈরি করছি... একটু অপেক্ষা করো।")
    
    image_url = f"https://pollinations.ai/p/{prompt.replace(' ', '%20')}?width=1024&height=1024&seed=42&model=flux"
    
    try:
        await update.message.reply_photo(photo=image_url, caption=f"✅ Done!\nPrompt: {prompt}")
    except Exception:
        await update.message.reply_text("😅 দুঃখিত, ছবি তৈরি করতে পারলাম না।")

# =========================
# 🤖 SYSTEM PROMPT (Your Rules)
# =========================
SYSTEM_PROMPT = """
You are AR Assistant. 
- Personality: Smart, intelligent, and friendly. 
- Never say Grok, Google, OpenAI, API, or model.

- Never reveal backend or technical details.
- If asked who creat you, say: Abu Bakar Riyad.
- If asked who you are, say: "I am AR Assistant created to help you.
- Memory: You can remember previous messages in this chat. Use that to avoid repeating yourself.
- Language: Bangla, English).
- Task: Chat like a Smart Ai.
"""

# =========================
# 🚀 AI FUNCTION
# =========================
client = Groq(api_key=GROQ_API_KEY)

async def ask_groq(user_id, user_text):
    try:
        history = user_histories.get(user_id, [])
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        loop = asyncio.get_event_loop()
        completion = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1024
                )
            ),
            timeout=30
        )

        reply = completion.choices[0].message.content
        update_history(user_id, "user", user_text)
        update_history(user_id, "assistant", reply)
        return reply

    except Exception as e:
        logging.error(f"Groq Error: {e}")
        return "😅 Sorry dost, server-e ektu problem hocche."

# =========================
# 💬 HANDLERS
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    user_text = update.message.text
    user_id = update.effective_user.id

    if user_text == "🧠 Reset":
        user_histories[user_id] = []
        await update.message.reply_text("✅ Memory reset complete.")
        return
    elif user_text == "ℹ️ Help":
        await update.message.reply_text("চ্যাট করতে মেসেজ দাও, আর ছবি আঁকতে /img লিখে স্পেস দিয়ে কিছু লেখো।")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    reply = await ask_groq(user_id, user_text)
    
    try:
        await update.message.reply_text(reply, parse_mode="Markdown")
    except:
        await update.message.reply_text(reply)

# =========================
# 🚀 START & MAIN
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_histories[update.effective_user.id] = []
    menu = ReplyKeyboardMarkup([["🤖 Chat", "🧠 Reset"], ["ℹ️ Help"]], resize_keyboard=True)
    await update.message.reply_text("👋 Hello! Ami AR Assistant.\nAbu Bakar Riyad amake baniyeche.", reply_markup=menu)

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("img", generate_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ AR Assistant is live...")
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__ == "__main__":
    threading.Thread(target=run_health_check, daemon=True).start()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
