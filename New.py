import telebot
from groq import Groq
from supabase import create_client

# --- API KEYS & CONFIG ---
TELEGRAM_TOKEN = '8359880624:AAEieOIdToP_HtRqIj1bObYt1laBTydOP9c'
GROQ_API_KEY = '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'
SUPABASE_URL = 'https://hterqqkbwxmvqyddqkps.supabase.co'
SUPABASE_KEY = 'sb_publishable_bsIXUhhLXArlMB6EovNLFA_zfXe09h8'

# Setup Clients
bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_personality_prompt(history_context):
    return f"""
    Tumi hobe Abu Bakr Riad-er ekta Digital Twin/Clone. 
    Kotha bolar niyom:
    1. Language: Shudhu Banglish (Bengali written in English letters) use korbe.
    2. Identity: Tumi 19 bochorer ekta chele, Dhaka-te thako. Football khela tomar hobby. 
    3. Profession/Life: Tumi 'Siam Fabric' e warehouse management koro ar inventory dekho. Japanese N5 shikcho.
    4. Style: Ekdom bondhur moto kotha bolbe, beshi polite ba AI-er moto hobar dorkar nai. 
    5. Memory: Nicher history mone rekhe kotha bolbe jeno purono kotha na bhulo:
    {history_context}
    """

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = str(message.chat.id)
    user_text = message.text

    try:
        # ১. ডাটাবেস থেকে স্মৃতি আনা
        history_data = supabase.table("chat_history").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(5).execute()
        
        context = ""
        if history_data.data:
            for chat in reversed(history_data.data):
                context += f"User: {chat['user_message']}\nClone: {chat['bot_reply']}\n"

        # ২. Groq (Llama 3) দিয়ে উত্তর তৈরি
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": get_personality_prompt(context)},
                {"role": "user", "content": user_text}
            ],
            model="llama-3.1-70b-versatile",
        )
        
        bot_reply = chat_completion.choices[0].message.content

        # ৩. নতুন স্মৃতি ডাটাবেসে সেভ করা
        supabase.table("chat_history").insert({
            "user_id": user_id, 
            "user_message": user_text, 
            "bot_reply": bot_reply
        }).execute()

        bot.reply_to(message, bot_reply)

    except Exception as e:
        print(f"Error: {e}")
        bot.reply_to(message, "Mama, system-e ektu jhamela hoise. Memory save korte parchi na mone hoy!")

# Run the bot
print("Abu Bakr Riad AI is now Online!")
bot.polling()
