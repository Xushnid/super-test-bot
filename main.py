import asyncio
import json
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

# --- SOZLAMALAR ---
TOKEN = os.getenv("BOT_TOKEN")  # Tokenni Renderdan oladi
# QUYIDAGI LINKNI 3-QADAMDA O'ZGARTIRAMIZ:
WEB_APP_URL = "https://xushnid.github.io/super-test-bot/" 

# --- BOT VA BAZA ---
bot = Bot(token=TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# Bazaga ulanish (Foydalanuvchilarni eslab qolish uchun)
conn = sqlite3.connect("users.db")
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
conn.commit()

# --- HANDLERLAR ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    
    # Foydalanuvchini bazaga qo'shamiz (agar yo'q bo'lsa)
    cursor.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
    conn.commit()

    # Web App tugmasi
    btn = KeyboardButton(text="✍️ Testni Boshlash", web_app=WebAppInfo(url=WEB_APP_URL))
    markup = ReplyKeyboardMarkup(keyboard=[[btn]], resize_keyboard=True)
    
    await message.answer("Test yechish uchun tugmani bosing 👇", reply_markup=markup)

@dp.message(F.web_app_data)
async def handle_result(message: types.Message):
    # WebAppdan ma'lumotni olamiz
    data = json.loads(message.web_app_data.data)
    name = data.get("name")
    group = data.get("group")
    score = data.get("score")
    total = data.get("total")

    # Xabar matni
    text = (f"📢 **Yangi Natija!**\n\n"
            f"👤 **Talaba:** {name}\n"
            f"🎓 **Guruh:** {group}\n"
            f"✅ **Baho:** {score} / {total}")

    # Barcha foydalanuvchilarga tarqatish
    cursor.execute("SELECT id FROM users")
    all_users = cursor.fetchall()

    for user in all_users:
        user_id = user[0]
        try:
            await bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
        except:
            pass # Agar birov botni bloklagan bo'lsa, o'tkazib yuboramiz

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    if TOKEN:
        asyncio.run(main())
