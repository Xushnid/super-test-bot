import asyncio
import json
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
from aiohttp import web
import aiohttp_cors

# --- SOZLAMALAR ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1917817674  # <-- O'Z ID RAQAMINGIZNI YOZING! (userinfobot orqali oling)
# Github Pages Linki
WEB_APP_URL = "https://xushnid.github.io/super-test-bot/" 
# ==========================================


bot = Bot(token=TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# --- BAZA ---
conn = sqlite3.connect("users.db")
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
cursor.execute("CREATE TABLE IF NOT EXISTS tests (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, questions TEXT, is_active INTEGER DEFAULT 0)")
conn.commit()

# --- STATES ---
class TestState(StatesGroup):
    waiting_for_name = State()
    waiting_for_file = State()

# --- YORDAMCHI FUNKSIYA ---
async def refresh_test_menu(message: types.Message, test_id: int):
    cursor.execute("SELECT name, is_active FROM tests WHERE id = ?", (test_id,))
    test = cursor.fetchone()
    
    if not test:
        try: await message.edit_text("❌ Test topilmadi.")
        except: pass
        return

    name, is_active = test
    status_text = "🟢 Aktiv" if is_active else "🔴 Aktiv emas"
    
    btn_status = InlineKeyboardButton(text="🔴 O'chirish" if is_active else "🟢 Yoqish", callback_data=f"toggle_{test_id}")
    btn_back = InlineKeyboardButton(text="🔙 Ortga", callback_data="admin_tests")
    
    try:
        await message.edit_text(
            f"⚙️ <b>Test sozlamalari:</b>\n\n🆔 ID: {test_id}\n📝 Nom: {name}\n📊 Holat: {status_text}", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn_status], [btn_back]]),
            parse_mode="HTML"
        )
    except:
        pass

# --- HANDLERLAR ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
    conn.commit()

    web_app_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✍️ Test yechish", web_app=WebAppInfo(url=WEB_APP_URL))]],
        resize_keyboard=True
    )

    if user_id == ADMIN_ID:
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Testlarni boshqarish", callback_data="admin_tests")]
        ])
        await message.answer("Salom Admin! Testni sinash uchun pastdagi tugmani bosing 👇", reply_markup=web_app_kb)
        await message.answer("Yoki testlarni tahrirlang:", reply_markup=admin_kb)
    else:
        await message.answer("Test yechish uchun tugmani bosing 👇", reply_markup=web_app_kb)

@dp.callback_query(F.data == "admin_tests")
async def view_tests(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    cursor.execute("SELECT id, name, is_active FROM tests")
    tests = cursor.fetchall()

    buttons = []
    for t_id, t_name, t_active in tests:
        status = "🟢" if t_active else "🔴"
        buttons.append([InlineKeyboardButton(text=f"{status} {t_name}", callback_data=f"edit_test_{t_id}")])
    
    buttons.append([InlineKeyboardButton(text="➕ Yangi test yaratish", callback_data="new_test")])
    await call.message.edit_text("📂 Barcha testlar ro'yxati:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "new_test")
async def ask_name(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 <b>Yangi test nomini yozing:</b>", parse_mode="HTML")
    await state.set_state(TestState.waiting_for_name)
    await state.update_data(msg_id=call.message.message_id)

@dp.message(TestState.waiting_for_name)
async def receive_name(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    data = await state.get_data()
    msg_id = data.get('msg_id')
    test_name = message.text

    try: await message.delete()
    except: pass

    await state.update_data(test_name=test_name)
    try:
        await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=f"✅ Nom: {test_name}\n\n📂 Endi <b>test.txt</b> faylini yuklang (JSON formatda).", parse_mode="HTML")
    except:
        msg = await message.answer(f"✅ Nom: {test_name}\n\n📂 Endi <b>test.txt</b> faylini yuklang.")
        await state.update_data(msg_id=msg.message_id)
    await state.set_state(TestState.waiting_for_file)

@dp.message(TestState.waiting_for_file, F.document)
async def receive_file(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    data = await state.get_data()
    msg_id = data.get('msg_id')
    test_name = data.get('test_name')

    file_id = message.document.file_id
    file = await bot.get_file(file_id)
    file_content = await bot.download_file(file.file_path)
    json_content = file_content.read().decode('utf-8')

    try:
        json.loads(json_content)
    except:
        await message.answer("❌ Fayl xato formatda!")
        return

    cursor.execute("INSERT INTO tests (name, questions, is_active) VALUES (?, ?, 0)", (test_name, json_content))
    conn.commit()

    try: await message.delete()
    except: pass
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Ro'yxatga qaytish", callback_data="admin_tests")]])
    try:
        await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=f"✅ <b>{test_name}</b> saqlandi!", reply_markup=kb, parse_mode="HTML")
    except:
        await message.answer(f"✅ <b>{test_name}</b> saqlandi!", reply_markup=kb, parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data.startswith("edit_test_"))
async def edit_single_test(call: types.CallbackQuery):
    try:
        test_id = int(call.data.split("_")[2])
        await refresh_test_menu(call.message, test_id)
    except: pass

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_status(call: types.CallbackQuery):
    try:
        test_id = int(call.data.split("_")[1])
        cursor.execute("SELECT is_active FROM tests WHERE id = ?", (test_id,))
        res = cursor.fetchone()
        if res:
            new_status = 0 if res[0] else 1
            cursor.execute("UPDATE tests SET is_active = ? WHERE id = ?", (new_status, test_id))
            conn.commit()
            await call.answer("Status o'zgardi!")
            await refresh_test_menu(call.message, test_id)
    except: pass

@dp.message(F.web_app_data)
async def handle_result(message: types.Message):
    data = json.loads(message.web_app_data.data)
    test_name = data.get("test_name")
    student_name = data.get("student_name")
    score = data.get("score")
    total = data.get("total")
    username = f"@{message.from_user.username}" if message.from_user.username else "mavjud emas"
    
    text = f"🏁 **Test Yakunlandi!**\n\n📚 {test_name}\n👤 {student_name}\n🔗 {username}\n✅ {score} / {total}"
    await message.answer(text, parse_mode="Markdown")
    if message.from_user.id != ADMIN_ID:
        try: await bot.send_message(chat_id=ADMIN_ID, text=f"🔔 **Yangi Natija!**\n\n{text}", parse_mode="Markdown")
        except: pass

# --- SERVER QISMI (TUZATILGAN) ---
routes = web.RouteTableDef()

@routes.get('/')
async def hello(request):
    return web.Response(text="Bot ishlab turibdi 🚀")

@routes.get('/api/tests')
async def get_active_tests(request):
    cursor.execute("SELECT id, name FROM tests WHERE is_active = 1")
    tests = [{"id": t[0], "name": t[1]} for t in cursor.fetchall()]
    # TUZATILDI: headers qo'lda qo'shilmadi, aiohttp_cors o'zi qo'shadi
    return web.json_response(tests)

@routes.get('/api/test/{id}')
async def get_test_questions(request):
    test_id = request.match_info['id']
    cursor.execute("SELECT questions, name FROM tests WHERE id = ? AND is_active = 1", (test_id,))
    row = cursor.fetchone()
    if row:
        # TUZATILDI: headers qo'lda qo'shilmadi
        return web.json_response({"name": row[1], "questions": json.loads(row[0])})
    return web.json_response({"error": "Test topilmadi"}, status=404)

async def start_server():
    app = web.Application()
    app.add_routes(routes)
    
    # CORS SOZLAMALARI
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*",
        )
    })
    
    # Barcha routelarga avtomatik CORS qo'shish
    for route in list(app.router.routes()):
        cors.add(route)
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    await start_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    if TOKEN:
        asyncio.run(main())
