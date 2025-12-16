import asyncio
import json
import logging
import os
import random
import string
from datetime import datetime, timedelta
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
WEB_APP_URL = "https://xushnid.github.io/super-test-bot/" 

bot = Bot(token=TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)
db_pool = None

# --- HEMIS FORMATINI PARSING QILISH ---
def parse_hemis_format(text):
    questions = []
    # 1. Savollarni ajratib olamiz (+++++)
    blocks = text.split('+++++')
    
    for block in blocks:
        block = block.strip()
        if not block: continue
        
        # 2. Savol va javoblarni ajratamiz (====)
        parts = block.split('====')
        if len(parts) < 2: continue # Yaroqsiz savol
        
        q_text = parts[0].strip()
        answers = []
        correct_index = -1
        
        # 3. Javoblarni tahlil qilamiz
        # parts[0] - savol, parts[1:] - javoblar
        answer_parts = parts[1:]
        
        valid_answers = []
        for i, ans in enumerate(answer_parts):
            ans = ans.strip()
            if not ans: continue
            
            # To'g'ri javob belgisi (#)
            if ans.startswith('#'):
                correct_index = len(valid_answers) # Hozirgi indeks
                ans = ans[1:].strip() # # ni olib tashlaymiz
            
            valid_answers.append(ans)
            
        if q_text and valid_answers and correct_index != -1:
            questions.append({
                "q": q_text,
                "a": valid_answers,
                "c": correct_index
            })
            
    return json.dumps(questions)

# --- BAZA ---
async def create_db_pool():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, ssl='require')
    async with db_pool.acquire() as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS users (id BIGINT PRIMARY KEY)")
        # start_time va end_time ni TIMESTAMP formatda saqlaymiz
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tests (
                id SERIAL PRIMARY KEY,
                owner_id BIGINT,
                name TEXT,
                unique_code TEXT UNIQUE,
                questions TEXT,
                is_active INTEGER DEFAULT 0,
                end_time TIMESTAMP
            )
        """)
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
    waiting_for_name = State()
    waiting_for_file = State()
    waiting_for_code = State()
    waiting_for_minutes = State() # Yangi state

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
    
    # Qolgan vaqtni ko'rsatish (Admin uchun)
    time_info = ""
    if test['is_active'] and test['end_time']:
        now = datetime.utcnow() # Server vaqti (UTC)
        remaining = test['end_time'] - now
        if remaining.total_seconds() > 0:
            mins = int(remaining.total_seconds() / 60)
            time_info = f"\n⏳ Tugashiga: {mins} daqiqa qoldi"
        else:
            time_info = "\n⌛️ Vaqt tugagan (Avtomatik o'chadi)"

    text = (f"🆔 Kod: <b>{test['unique_code']}</b>\n"
            f"📝 Nom: {test['name']}\n"
            f"📊 Holat: {status}{time_info}")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Aktivlashtirish" if not test['is_active'] else "🔴 To'xtatish", callback_data=f"toggle_{test_id}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del_{test_id}")],
        [InlineKeyboardButton(text="🔙 Testlarim", callback_data="my_tests")]
    ])
    
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
    
    await message.answer(f"Salom {message.from_user.full_name}! HEMIS test botiga xush kelibsiz.", reply_markup=kb)

# --- 1. TEST YARATISH ---
@dp.message(F.text == "➕ Test Yaratish")
async def create_test_start(message: types.Message, state: FSMContext):
    await message.answer("📝 Yangi test nomini yozing:")
    await state.set_state(BotStates.waiting_for_name)

@dp.message(BotStates.waiting_for_name)
async def create_test_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer(
        "📂 Endi test faylini yuklang (HEMIS formatda).\n\n"
        "Namuna:\n"
        "Savol matni?\n====\n#To'g'ri javob\n====\nXato javob\n+++++\nKeyingi savol...", 
        parse_mode="HTML"
    )
    await state.set_state(BotStates.waiting_for_file)

@dp.message(BotStates.waiting_for_file, F.document)
async def create_test_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    file = await bot.get_file(message.document.file_id)
    content = (await bot.download_file(file.file_path)).read().decode('utf-8')
    
    # HEMIS PARSING
    try:
        # Avval JSON ekanligini tekshirib ko'ramiz (eski format uchun)
        json.loads(content) 
        final_content = content
    except:
        # Agar JSON bo'lmasa, HEMIS deb qabul qilamiz
        try:
            final_content = parse_hemis_format(content)
            # Agar bo'sh bo'lsa
            if final_content == "[]":
                await message.answer("❌ Fayldan savollar topilmadi. Formatni tekshiring.")
                return
        except Exception as e:
            await message.answer(f"❌ Xatolik: {e}")
            return

    unique_code = generate_code()
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO tests (owner_id, name, unique_code, questions, is_active) 
            VALUES ($1, $2, $3, $4, 0)
        """, message.from_user.id, data['name'], unique_code, final_content)
    
    await message.answer(f"✅ Test yuklandi!\n🔑 Kod: <b>{unique_code}</b>\n\n'Mening Testlarim' bo'limidan faollashtiring.", parse_mode="HTML")
    await state.clear()

# --- 2. MENING TESTLARIM ---
@dp.message(F.text == "📂 Mening Testlarim")
async def my_tests_list(message: types.Message):
    async with db_pool.acquire() as conn:
        tests = await conn.fetch("SELECT id, name, unique_code, is_active FROM tests WHERE owner_id = $1 ORDER BY id DESC", message.from_user.id)
    
    if not tests:
        await message.answer("Sizda testlar yo'q.")
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
    await call.answer("O'chirildi.")
    await back_to_my_tests(call)

# --- 3. TESTNI YOQISH (DAQIQA BILAN) ---
@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_test_status(call: types.CallbackQuery, state: FSMContext):
    test_id = int(call.data.split("_")[1])
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT is_active FROM tests WHERE id = $1", test_id)
        
        if test['is_active']:
            # O'chirish
            await conn.execute("UPDATE tests SET is_active = 0, end_time = NULL WHERE id = $1", test_id)
            await call.answer("Test to'xtatildi")
            await show_test_menu(call, test_id)
        else:
            # Yoqish uchun daqiqa so'raymiz
            await state.update_data(test_id=test_id)
            await call.message.answer("⏱ Ushbu test necha daqiqa ochiq tursin?\n(Raqam yozing, masalan: 40)", parse_mode="HTML")
            await state.set_state(BotStates.waiting_for_minutes)

@dp.message(BotStates.waiting_for_minutes)
async def set_active_minutes(message: types.Message, state: FSMContext):
    try:
        minutes = int(message.text)
        if minutes <= 0: raise ValueError
        
        data = await state.get_data()
        test_id = data['test_id']
        
        # Tugash vaqtini hisoblaymiz (UTC bo'yicha)
        end_time = datetime.utcnow() + timedelta(minutes=minutes)
        
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE tests SET is_active = 1, end_time = $1 WHERE id = $2", end_time, test_id)
        
        await message.answer(f"✅ Test {minutes} daqiqaga faollashtirildi!")
        await state.clear()
        
        # Menyuni qayta ko'rsatish qiyin, shunchaki xabar qoldiramiz
    except:
        await message.answer("❌ Iltimos, butun musbat son kiriting (masalan: 30).")

# --- 4. TEST YECHISH ---
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
        await message.answer("❌ Test topilmadi.")
        return
    
    if not test['is_active']:
        await message.answer("🚫 Test o'chirilgan.")
        return
    
    # Vaqt tekshiruvi (Server UTC vaqti bilan)
    if test['end_time'] and datetime.utcnow() > test['end_time']:
        # Vaqt tugagan bo'lsa avtomatik o'chirib qo'yamiz
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE tests SET is_active = 0 WHERE id = $1", test['id'])
        await message.answer("⌛️ Test vaqti tugab bo'lgan.")
        return

    app_link = f"{WEB_APP_URL}?code={code}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🚀 Boshlash: {test['name']}", web_app=WebAppInfo(url=app_link))]
    ])
    await message.answer("Testga kirish:", reply_markup=kb)
    await state.clear()

# --- WEB APP DATA ---
@dp.message(F.web_app_data)
async def handle_webapp_data(message: types.Message):
    data = json.loads(message.web_app_data.data)
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT owner_id, name FROM tests WHERE unique_code = $1", data['test_code'])
        await conn.execute("INSERT INTO results (test_code, user_id, score, total, full_name) VALUES ($1, $2, $3, $4, $5)", 
                           data['test_code'], message.from_user.id, data['score'], data['total'], data['student_name'])

    await message.answer(f"✅ Natija qabul qilindi: {data['score']}/{data['total']}")
    if test:
        try:
            await bot.send_message(test['owner_id'], f"🔔 <b>Yechim:</b> {test['name']}\n👤 {data['student_name']}\n📊 {data['score']}/{data['total']}", parse_mode="HTML")
        except: pass

# --- SERVER API ---
routes = web.RouteTableDef()
@routes.get('/')
async def home(request): return web.Response(text="Bot running")

@routes.get('/api/get_test')
async def api_get_test(request):
    code = request.query.get('code')
    if not code or not db_pool: return web.json_response({"error": "No code"}, status=400)
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT questions, name, end_time FROM tests WHERE unique_code = $1", code)
    
    if row:
        # Qolgan vaqtni sekundlarda hisoblab beramiz
        remaining_seconds = 0
        if row['end_time']:
            delta = row['end_time'] - datetime.utcnow()
            remaining_seconds = int(delta.total_seconds())
        
        # Vaqt tugagan bo'lsa
        if remaining_seconds <= 0:
             return web.json_response({"error": "Time expired"}, status=400)

        return web.json_response({
            "name": row['name'], 
            "questions": json.loads(row['questions']),
            "remaining_seconds": remaining_seconds 
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
    try: await start_server(); await dp.start_polling(bot)
    finally: await close_db_pool()

if __name__ == "__main__":
    if TOKEN: asyncio.run(main())
