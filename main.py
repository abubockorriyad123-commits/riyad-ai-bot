import os
import logging
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, ReplyKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from groq import Groq

# =========================
# 🔑 CONFIG & LOGGING
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

user_histories = {}
limit_info = {"remaining_tokens": "Unknown", "reset_time": "Unknown"}

# =========================
# 🧠 MEMORY LOGIC
# =========================
def update_history(user_id, role, content):
    if user_id not in user_histories:
        user_histories[user_id] = []
    user_histories[user_id].append({"role": role, "content": content})
    if len(user_histories[user_id]) > 8:
        user_histories[user_id] = user_histories[user_id][-8:]

# =========================
# 🤖 SYSTEM PROMPT (Abu Bakar Riyad's Specific Rules)
# =========================
SYSTEM_PROMPT = """
You are AR Assistant.
Developer: Abu Bakar Riyad.
Personality: Smart, Friendly, Human-like.
Rules:
- Never reveal technical details like APIs or Groq.
- If asked who created you, say: "Abu Bakar Riyad created me."
- Speak naturally in Bangla and English.
- Be helpful about inventory, Japanese learning (N5), or football if asked.
"""

# =========================
# 🚀 AI FUNCTION (Llama-3.1-8b-instant for better limit)
# =========================
client = Groq(api_key=GROQ_API_KEY)

async def ask_ai(user_id, user_text):
    global limit_info
    try:
        history = user_histories.get(user_id, [])
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        response = client.chat.completions.with_raw_response.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.7,
            max_tokens=800
        )

        limit_info["remaining_tokens"] = response.headers.get("x-ratelimit-remaining-tokens", "N/A")
        limit_info["reset_time"] = response.headers.get("x-ratelimit-reset-tokens", "N/A")

        completion = response.parse()
        reply = completion.choices[0].message.content
        
        update_history(user_id, "user", user_text)
        update_history(user_id, "assistant", reply)
        return reply

    except Exception as e:
        logging.error(f"Error: {e}")
        if "rate_limit_exceeded" in str(e):
            return "⚠️ Sorry dost, amar daily free limit sesh hoye geche! Abar ektu por try koro."
        return "😅 Ektu technical problem hocche."

# =========================
# 📝 NOTE & BALANCE COMMANDS
# =========================
async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note_text = " ".join(context.args)
    if not note_text:
        await update.message.reply_text("❌ Kicchu to lekho! Example: `/note Stock updated for Siam Fabric`", parse_mode="Markdown")
        return
    
    # Ekhane tumi Supabase code add korte parbe. Ekhonkar jonno confirm korche.
    await update.message.reply_text(f"✅ Note saved: {note_text}")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📊 *Usage Status:*\n\n"
        f"🔹 Remaining Tokens: `{limit_info['remaining_tokens']}`\n"
        f"🔹 Reset Time: `{limit_info['reset_time']}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# =========================
# 🚀 START & MAIN
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = ReplyKeyboardMarkup([["🤖 Chat", "🧠 Reset"], ["📊 Balance", "📝 Note"]], resize_keyboard=True)
    await update.message.reply_text("👋 Hello! Ami AR Assistant. Abu Bakar Riyad amake baniyeche.", reply_markup=menu)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_text = update.message.text
    user_id = update.effective_user.id

    if user_text == "📊 Balance":
        await balance(update, context)
        return
    elif user_text == "🧠 Reset":
        user_histories[user_id] = []
        await update.message.reply_text("✅ Memory reset complete.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    reply = await ask_ai(user_id, user_text)
    await update.message.reply_text(reply, parse_mode="Markdown")

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("note", save_note))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()

if __name__ == "__main__":
    def run_health():
        port = int(os.environ.get("PORT", 8080))
        HTTPServer(("0.0.0.0", port), BaseHTTPRequestHandler).serve_forever()
    threading.Thread(target=run_health, daemon=True).start()
    asyncio.run(main())
