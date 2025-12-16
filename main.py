import asyncio
import json
import logging
import os
import random
import string
from datetime import datetime
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
from aiohttp import web
import aiohttp_cors

# SOZLAMALAR
TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
# WEB_APP_URL oxirida / belgisi bo'lsin!
WEB_APP_URL = "https://xushnid.github.io/super-test-bot/" 

bot = Bot(token=TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)
db_pool = None

# --- BAZA ---
async def create_db_pool():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, ssl='require')
    async with db_pool.acquire() as conn:
        # Users jadvali
        await conn.execute("CREATE TABLE IF NOT EXISTS users (id BIGINT PRIMARY KEY)")
        # Tests jadvali (Yangilangan)
        # owner_id: Test egasi
        # unique_code: 5 xonali kod
        # start_time, end_time: Test vaqti (matn sifatida saqlaymiz: YYYY-MM-DD HH:MM)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tests (
                id SERIAL PRIMARY KEY,
                owner_id BIGINT,
                name TEXT,
                unique_code TEXT UNIQUE,
                questions TEXT,
                is_active INTEGER DEFAULT 0,
                start_time TEXT,
                end_time TEXT
            )
        """)
        # Natijalar jadvali (Qayta topshirishni oldini olish yoki statistika uchun)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id SERIAL PRIMARY KEY,
                test_code TEXT,
                user_id BIGINT,
                score INTEGER,
                total INTEGER,
                full_name TEXT
            )
        """)

async def close_db_pool():
    if db_pool: await db_pool.close()

# --- STATES ---
class BotStates(StatesGroup):
    # Test yaratish
    waiting_for_name = State()
    waiting_for_file = State()
    # Test yechish
    waiting_for_code = State()
    # Vaqt sozlash
    waiting_for_start_time = State()
    waiting_for_end_time = State()

# --- YORDAMCHI: 5 xonali kod yaratish ---
def generate_code():
    return ''.join(random.choices(string.digits, k=5))

# --- YORDAMCHI: Test menyusi ---
async def show_test_menu(message, test_id):
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT * FROM tests WHERE id = $1", test_id)
    
    if not test:
        await message.answer("Test topilmadi.")
        return

    status = "🟢 Aktiv" if test['is_active'] else "🔴 Deaktiv"
    times = f"\n⏳ Vaqt: {test['start_time']} - {test['end_time']}" if test['start_time'] else "\n⏳ Vaqt belgilanmagan"
    
    text = (f"🆔 Kod: <b>{test['unique_code']}</b>\n"
            f"📝 Nom: {test['name']}\n"
            f"📊 Holat: {status}{times}")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Yoqish / Vaqt sozlash" if not test['is_active'] else "🔴 O'chirish", callback_data=f"toggle_{test_id}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del_{test_id}")],
        [InlineKeyboardButton(text="🔙 Testlarim", callback_data="my_tests")]
    ])
    
    # Message yoki CallbackQuery ekanligini aniqlash
    if isinstance(message, types.CallbackQuery):
        await message.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

# --- ASOSIY MENYU ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING", user_id)
    
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✍️ Test Yechish"), KeyboardButton(text="➕ Test Yaratish")],
        [KeyboardButton(text="📂 Mening Testlarim")]
    ], resize_keyboard=True)
    
    await message.answer(f"Salom {message.from_user.full_name}! Botga xush kelibsiz.", reply_markup=kb)

# --- 1. TEST YARATISH ---
@dp.message(F.text == "➕ Test Yaratish")
async def create_test_start(message: types.Message, state: FSMContext):
    await message.answer("📝 Yangi test nomini yozing:")
    await state.set_state(BotStates.waiting_for_name)

@dp.message(BotStates.waiting_for_name)
async def create_test_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("📂 Endi <b>test.txt</b> faylini (JSON) yuklang.", parse_mode="HTML")
    await state.set_state(BotStates.waiting_for_file)

@dp.message(BotStates.waiting_for_file, F.document)
async def create_test_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    file = await bot.get_file(message.document.file_id)
    content = (await bot.download_file(file.file_path)).read().decode('utf-8')
    
    try:
        json.loads(content) # Validatsiya
    except:
        await message.answer("❌ Fayl formati xato JSON.")
        return

    # Unikal kod yaratish
    unique_code = generate_code()
    # Kod bazada bor-yo'qligini tekshirish (juda kam ehtimol, lekin...)
    async with db_pool.acquire() as conn:
        while await conn.fetchval("SELECT 1 FROM tests WHERE unique_code = $1", unique_code):
            unique_code = generate_code()
        
        await conn.execute("""
            INSERT INTO tests (owner_id, name, unique_code, questions, is_active) 
            VALUES ($1, $2, $3, $4, 0)
        """, message.from_user.id, data['name'], unique_code, content)
    
    await message.answer(f"✅ Test yaratildi!\n🔑 Test kodi: <b>{unique_code}</b>\n\nTest hozir 🔴 Deaktiv. 'Mening Testlarim' bo'limidan vaqt belgilab yoqing.", parse_mode="HTML")
    await state.clear()

# --- 2. MENING TESTLARIM (Boshqaruv) ---
@dp.message(F.text == "📂 Mening Testlarim")
async def my_tests_list(message: types.Message):
    async with db_pool.acquire() as conn:
        tests = await conn.fetch("SELECT id, name, unique_code, is_active FROM tests WHERE owner_id = $1 ORDER BY id DESC", message.from_user.id)
    
    if not tests:
        await message.answer("Sizda hali testlar yo'q.")
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'🟢' if t['is_active'] else '🔴'} {t['unique_code']} - {t['name']}", callback_data=f"view_{t['id']}")]
        for t in tests
    ])
    await message.answer("Sizning testlaringiz:", reply_markup=kb)

@dp.callback_query(F.data == "my_tests")
async def back_to_my_tests(call: types.CallbackQuery):
    await call.message.delete()
    await my_tests_list(call.message)

@dp.callback_query(F.data.startswith("view_"))
async def view_test_details(call: types.CallbackQuery):
    test_id = int(call.data.split("_")[1])
    await show_test_menu(call, test_id)

@dp.callback_query(F.data.startswith("del_"))
async def delete_test(call: types.CallbackQuery):
    test_id = int(call.data.split("_")[1])
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM tests WHERE id = $1", test_id)
    await call.answer("Test o'chirildi.")
    await back_to_my_tests(call)

# --- 3. TESTNI YOQISH (Vaqt sozlash) ---
@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_test_status(call: types.CallbackQuery, state: FSMContext):
    test_id = int(call.data.split("_")[1])
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT is_active FROM tests WHERE id = $1", test_id)
        
        if test['is_active']:
            # O'chirish
            await conn.execute("UPDATE tests SET is_active = 0 WHERE id = $1", test_id)
            await call.answer("Test o'chirildi")
            await show_test_menu(call, test_id)
        else:
            # Yoqish uchun vaqt so'raymiz
            await state.update_data(test_id=test_id)
            await call.message.answer("📅 Test BOSHLANISH vaqtini kiriting:\nFormat: <code>YYYY-MM-DD HH:MM</code>\nMisol: 2025-12-16 14:00", parse_mode="HTML")
            await state.set_state(BotStates.waiting_for_start_time)

@dp.message(BotStates.waiting_for_start_time)
async def set_start_time(message: types.Message, state: FSMContext):
    try:
        # Formatni tekshiramiz
        datetime.strptime(message.text, "%Y-%m-%d %H:%M")
        await state.update_data(start_time=message.text)
        await message.answer("📅 Test TUGASH vaqtini kiriting:\nFormat: <code>YYYY-MM-DD HH:MM</code>", parse_mode="HTML")
        await state.set_state(BotStates.waiting_for_end_time)
    except:
        await message.answer("❌ Format xato! Qaytadan kiriting (YYYY-MM-DD HH:MM)")

@dp.message(BotStates.waiting_for_end_time)
async def set_end_time(message: types.Message, state: FSMContext):
    try:
        end_dt = datetime.strptime(message.text, "%Y-%m-%d %H:%M")
        data = await state.get_data()
        start_dt = datetime.strptime(data['start_time'], "%Y-%m-%d %H:%M")
        
        if end_dt <= start_dt:
            await message.answer("❌ Tugash vaqti boshlanish vaqtidan katta bo'lishi kerak!")
            return

        test_id = data['test_id']
        async with db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE tests SET is_active = 1, start_time = $1, end_time = $2 WHERE id = $3
            """, data['start_time'], message.text, test_id)
        
        await message.answer(f"✅ Test faollashtirildi!\n{data['start_time']} dan {message.text} gacha ishlaydi.")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")

# --- 4. TEST YECHISH (Kod orqali kirish) ---
@dp.message(F.text == "✍️ Test Yechish")
async def solve_test_ask_code(message: types.Message, state: FSMContext):
    await message.answer("🔑 Test kodini kiriting (5 xonali):")
    await state.set_state(BotStates.waiting_for_code)

@dp.message(BotStates.waiting_for_code)
async def check_test_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT * FROM tests WHERE unique_code = $1", code)
    
    if not test:
        await message.answer("❌ Bunday kodli test topilmadi.")
        return
    
    # Vaqt va Status tekshiruvi
    now = datetime.now()
    if not test['is_active']:
        await message.answer("🚫 Bu test hozir o'chirilgan (Deaktiv).")
        return
    
    start_t = datetime.strptime(test['start_time'], "%Y-%m-%d %H:%M")
    end_t = datetime.strptime(test['end_time'], "%Y-%m-%d %H:%M")
    
    if now < start_t:
        await message.answer(f"⏳ Test hali boshlanmadi.\nBoshlanish vaqti: {test['start_time']}")
        return
    if now > end_t:
        await message.answer("⌛️ Test vaqti tugagan.")
        return

    # WebApp tugmasini beramiz (Linkda code parametrini jo'natamiz)
    # MUHIM: WEB_APP_URL oxirida '?' belgisi bilan parametr qo'shamiz
    app_link = f"{WEB_APP_URL}?code={code}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🚀 Testni Boshlash ({test['name']})", web_app=WebAppInfo(url=app_link))]
    ])
    await message.answer("Test topildi! Boshlash uchun bosing:", reply_markup=kb)
    await state.clear()

# --- WEB APP MA'LUMOTLARI ---
@dp.message(F.web_app_data)
async def handle_webapp_data(message: types.Message):
    data = json.loads(message.web_app_data.data)
    # data: {test_code, score, total, student_name, details}
    
    # Test egasini topamiz
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT owner_id, name FROM tests WHERE unique_code = $1", data['test_code'])
        # Natijani bazaga saqlash (ixtiyoriy)
        await conn.execute("INSERT INTO results (test_code, user_id, score, total, full_name) VALUES ($1, $2, $3, $4, $5)", 
                           data['test_code'], message.from_user.id, data['score'], data['total'], data['student_name'])

    # 1. Talabaga xabar
    student_text = (f"✅ <b>Test yakunlandi!</b>\n"
                    f"📚 Test: {test['name']}\n"
                    f"📊 Natija: {data['score']} / {data['total']}")
    await message.answer(student_text, parse_mode="HTML")

    # 2. Test egasiga xabar
    if test:
        owner_text = (f"🔔 <b>Yangi yechim!</b>\n"
                      f"📚 Test: {test['name']} ({data['test_code']})\n"
                      f"👤 Talaba: {data['student_name']}\n"
                      f"📊 Natija: {data['score']} / {data['total']}")
        try:
            await bot.send_message(test['owner_id'], owner_text, parse_mode="HTML")
        except: pass

# --- SERVER API ---
routes = web.RouteTableDef()

@routes.get('/')
async def home(request): return web.Response(text="Bot is running")

@routes.get('/api/get_test')
async def api_get_test(request):
    code = request.query.get('code')
    if not code or not db_pool: return web.json_response({"error": "No code"}, status=400)
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT questions, name, end_time FROM tests WHERE unique_code = $1", code)
    
    if row:
        return web.json_response({
            "name": row['name'], 
            "questions": json.loads(row['questions']),
            "end_time": row['end_time']
        })
    return web.json_response({"error": "Not found"}, status=404)

async def start_server():
    app = web.Application()
    app.add_routes(routes)
    cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*", allow_methods="*")})
    for route in list(app.router.routes()): cors.add(route)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    await create_db_pool()
    try:
        await start_server()
        await dp.start_polling(bot)
    finally:
        await close_db_pool()

if __name__ == "__main__":
    if TOKEN: asyncio.run(main())
