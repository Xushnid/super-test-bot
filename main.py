import asyncio
import json
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, FSInputFile
from aiohttp import web
import aiohttp_cors # Buni requirements.txt ga qo'shish kerak bo'ladi

# --- SOZLAMALAR ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1917817674  # <-- O'Z ID RAQAMINGIZNI YOZING! (userinfobot orqali oling)
# Github Pages Linki
WEB_APP_URL = "https://xushnid.github.io/super-test-bot/" 

bot = Bot(token=TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# --- BAZA ---
conn = sqlite3.connect("users.db")
cursor = conn.cursor()
# Foydalanuvchilar
cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
# Testlar jadvali: id, nom, savollar(json), status(0/1)
cursor.execute("CREATE TABLE IF NOT EXISTS tests (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, questions TEXT, is_active INTEGER DEFAULT 0)")
conn.commit()

# --- STATES (Admin ketma-ketligi uchun) ---
class TestState(StatesGroup):
    waiting_for_name = State()
    waiting_for_file = State()

# --- ADMIN PANEL QISMI ---

# 1. Admin uchun /start (Panelni ochish)
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
    conn.commit()

    if user_id == ADMIN_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Testlarni boshqarish", callback_data="admin_tests")]
        ])
        await message.answer(f"Salom Admin! Boshqaruv paneli:", reply_markup=kb)
    else:
        # Oddiy foydalanuvchi uchun faqat WebApp tugmasi
        kb = types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="✍️ Test yechish", web_app=WebAppInfo(url=WEB_APP_URL))]],
            resize_keyboard=True
        )
        await message.answer("Test yechish uchun pastdagi tugmani bosing 👇", reply_markup=kb)

# 2. Testlar ro'yxatini ko'rsatish
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
    buttons.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="main_menu")]) # Main menu funksiyasini o'zingiz qo'shishingiz mumkin yoki shunchaki yopiladi

    await call.message.edit_text("📂 Barcha testlar ro'yxati:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# 3. Yangi test yaratish - Nom so'rash
@dp.callback_query(F.data == "new_test")
async def ask_name(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 <b>Yangi test nomini yozing:</b>\n(Masalan: Matematika 1-variant)", parse_mode="HTML")
    await state.set_state(TestState.waiting_for_name)
    # Eslatib qolamiz qaysi xabarni edit qilish kerakligini
    await state.update_data(msg_id=call.message.message_id)

# 4. Nomni qabul qilish va Fayl so'rash
@dp.message(TestState.waiting_for_name)
async def receive_name(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    data = await state.get_data()
    msg_id = data.get('msg_id')
    test_name = message.text

    # User xabarini o'chiramiz (chat toza turishi uchun)
    try: await message.delete()
    except: pass

    await state.update_data(test_name=test_name)
    
    # Bot xabarini tahrirlaymiz
    await bot.edit_message_text(
        chat_id=message.chat.id, 
        message_id=msg_id, 
        text=f"✅ Nom: {test_name}\n\n📂 Endi <b>test.txt</b> faylini yuklang (JSON formatda).",
        parse_mode="HTML"
    )
    await state.set_state(TestState.waiting_for_file)

# 5. Faylni qabul qilish va Bazaga saqlash
@dp.message(TestState.waiting_for_file, F.document)
async def receive_file(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    data = await state.get_data()
    msg_id = data.get('msg_id')
    test_name = data.get('test_name')

    # Faylni yuklab o'qiymiz
    file_id = message.document.file_id
    file = await bot.get_file(file_id)
    file_content = await bot.download_file(file.file_path)
    json_content = file_content.read().decode('utf-8')

    # JSON to'g'riligini tekshirish
    try:
        json.loads(json_content)
    except:
        await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text="❌ Fayl xato formatda! Iltimos to'g'ri JSON fayl yuklang.")
        try: await message.delete()
        except: pass
        return

    # Bazaga yozish
    cursor.execute("INSERT INTO tests (name, questions, is_active) VALUES (?, ?, 0)", (test_name, json_content))
    conn.commit()

    try: await message.delete()
    except: pass

    # Admin panelga qaytish (Testlar ro'yxatiga)
    # Biroz "hack": view_tests funksiyasini chaqirish uchun soxta callback yasaymiz
    await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text="✅ Test saqlandi!")
    # Aslida bu yerda to'g'ridan-to'g'ri menyuga qaytgan ma'qul, lekin hozircha shunchaki xabar:
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Ro'yxatga qaytish", callback_data="admin_tests")]])
    await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=f"✅ <b>{test_name}</b> muvaffaqiyatli qo'shildi!", reply_markup=kb, parse_mode="HTML")
    await state.clear()

# 6. Testni boshqarish (Aktiv/Deaktiv)
@dp.callback_query(F.data.startswith("edit_test_"))
async def edit_single_test(call: types.CallbackQuery):
    test_id = int(call.data.split("_")[2])
    cursor.execute("SELECT name, is_active FROM tests WHERE id = ?", (test_id,))
    test = cursor.fetchone()
    
    if not test:
        await call.answer("Test topilmadi", show_alert=True)
        return

    name, is_active = test
    status_text = "🟢 Aktiv" if is_active else "🔴 Aktiv emas"
    
    # Tugmalar
    btn_status = InlineKeyboardButton(text="🔴 O'chirish" if is_active else "🟢 Yoqish", callback_data=f"toggle_{test_id}")
    btn_back = InlineKeyboardButton(text="🔙 Ortga", callback_data="admin_tests")
    
    await call.message.edit_text(
        f"⚙️ <b>Test sozlamalari:</b>\n\n🆔 ID: {test_id}\n📝 Nom: {name}\n📊 Holat: {status_text}", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn_status], [btn_back]]),
        parse_mode="HTML"
    )

# 7. Statusni o'zgartirish
@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_status(call: types.CallbackQuery):
    test_id = int(call.data.split("_")[1])
    cursor.execute("SELECT is_active FROM tests WHERE id = ?", (test_id,))
    current_status = cursor.fetchone()[0]
    
    new_status = 0 if current_status else 1
    cursor.execute("UPDATE tests SET is_active = ? WHERE id = ?", (new_status, test_id))
    conn.commit()
    
    # Menyuni yangilash uchun edit_single_test ni qayta chaqiramiz
    await edit_single_test(call) # Recursion emulyatsiyasi (Data o'zgartirib chaqirish kerak aslida, lekin bu yerda call.data edit_test_ID ga o'xshash bo'lishi kerak)
    # Oson yo'li: shunchaki xabar berib, yana menyuni chizish
    await call.answer("Status o'zgardi!")

# --- WEB APP NATIJASINI QABUL QILISH ---
@dp.message(F.web_app_data)
async def handle_result(message: types.Message):
    data = json.loads(message.web_app_data.data)
    
    test_name = data.get("test_name")
    student_name = data.get("student_name") # Formadan kelgan ism
    score = data.get("score")
    total = data.get("total")
    
    username = f"@{message.from_user.username}" if message.from_user.username else "Mavjud emas"
    
    result_text = (
        f"🏁 **Test Yakunlandi!**\n\n"
        f"📚 **Test:** {test_name}\n"
        f"👤 **Talaba:** {student_name}\n"
        f"🔗 **Username:** {username}\n"
        f"✅ **Natija:** {score} / {total}"
    )

    # 1. Talabaga yuborish
    await message.answer(result_text, parse_mode="Markdown")
    
    # 2. Adminga yuborish
    if message.from_user.id != ADMIN_ID:
        await bot.send_message(chat_id=ADMIN_ID, text=f"🔔 **Yangi Natija!**\n\n{result_text}", parse_mode="Markdown")


# --- API QISMI (Render Server + API) ---
routes = web.RouteTableDef()

@routes.get('/')
async def hello(request):
    return web.Response(text="Bot is running")

# 1. Aktiv testlar ro'yxatini berish
@routes.get('/api/tests')
async def get_active_tests(request):
    cursor.execute("SELECT id, name FROM tests WHERE is_active = 1")
    tests = cursor.fetchall()
    tests_json = [{"id": t[0], "name": t[1]} for t in tests]
    return web.json_response(tests_json, headers={"Access-Control-Allow-Origin": "*"})

# 2. Konkret bitta test savollarini berish
@routes.get('/api/test/{id}')
async def get_test_questions(request):
    test_id = request.match_info['id']
    cursor.execute("SELECT questions, name FROM tests WHERE id = ? AND is_active = 1", (test_id,))
    row = cursor.fetchone()
    
    if row:
        questions = json.loads(row[0])
        return web.json_response({"name": row[1], "questions": questions}, headers={"Access-Control-Allow-Origin": "*"})
    else:
        return web.json_response({"error": "Test topilmadi"}, status=404, headers={"Access-Control-Allow-Origin": "*"})

async def start_server():
    app = web.Application()
    app.add_routes(routes)
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
