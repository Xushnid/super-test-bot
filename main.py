import asyncio
import json
import logging
import os
import sqlite3
import sys
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiohttp import web # <-- Render uchun kerak

# --- SOZLAMALAR ---
TOKEN = os.getenv("BOT_TOKEN")
# O'ZINGIZNING GITHUB SAHIFA LINKINGIZNI SHU YERGA QAYTADAN QO'YING:
WEB_APP_URL = "https://xushnid.github.io/super-test-bot/" 

bot = Bot(token=TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# --- BAZA ---
conn = sqlite3.connect("users.db")
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
conn.commit()

# --- HANDLERLAR ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
    conn.commit()

    btn = KeyboardButton(text="✍️ Testni Boshlash", web_app=WebAppInfo(url=WEB_APP_URL))
    markup = ReplyKeyboardMarkup(keyboard=[[btn]], resize_keyboard=True)
    
    await message.answer("Test yechish uchun tugmani bosing 👇", reply_markup=markup)

@dp.message(F.web_app_data)
async def handle_result(message: types.Message):
    data = json.loads(message.web_app_data.data)
    name = data.get("name")
    group = data.get("group")
    score = data.get("score")
    total = data.get("total")

    text = (f"📢 **Yangi Natija!**\n\n"
            f"👤 **Talaba:** {name}\n"
            f"🎓 **Guruh:** {group}\n"
            f"✅ **Baho:** {score} / {total}")

    cursor.execute("SELECT id FROM users")
    all_users = cursor.fetchall()
    for user in all_users:
        try:
            await bot.send_message(chat_id=user[0], text=text, parse_mode="Markdown")
        except:
            pass

# --- RENDER UCHUN MAXSUS QISM (FAKE WEB SERVER) ---
async def health_check(request):
    return web.Response(text="Bot ishlab turibdi! (Render uchun)")

async def start_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render o'zi beradigan PORT ni olamiz yoki 8080 ni ishlatamiz
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    # Ikkita ishni bir vaqtda qilamiz: Serverni yoqamiz va Botni ishlatamiz
    await start_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    if TOKEN:
        asyncio.run(main())
