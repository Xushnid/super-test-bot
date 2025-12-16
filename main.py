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

# --- HEMIS FORMATINI PARSING QILISH (YANGILANGAN) ---
def parse_hemis_format(text):
    questions = []
    
    # 1. Tozalash: Windows formatdagi qator tashlashni to'g'irlash
    text = text.replace('\r\n', '\n').strip()
    
    # 2. Bloklarga bo'lish
    blocks = text.split('+++++')
    
    for block in blocks:
        block = block.strip()
        if not block: continue
        
        # 3. Savol va javoblarni ajratish
        # Ba'zan ==== belgisi yangi qatorda bo'lmasligi mumkin, shuning uchun \n ni inobatga olamiz
        parts = block.split('====')
        
        # Agar ==== belgisi topilmasa yoki yetarli bo'lmasa
        if len(parts) < 2: 
            continue 
        
        q_text = parts[0].strip()
        answers = []
        correct_index = -1
        
        # Javoblarni yig'ish
        valid_answers = []
        answer_parts = parts[1:]
        
        for ans in answer_parts:
            ans = ans.strip()
            if not ans: continue
            
            # To'g'ri javobni aniqlash
            if ans.startswith('#'):
                correct_index = len(valid_answers)
                ans = ans[1:].strip()
            
            valid_answers.append(ans)
            
        # Agar savol matni bor bo'lsa va javoblar bo'lsa va to'g'ri javob belgilangan bo'lsa
        if q_text and valid_answers and correct_index != -1:
            questions.append({
                "q": q_text,
                "a": valid_answers,
                "c": correct_index
            })
            
    return json.dumps(questions)

# --- BAZA (O'zgarmadi) ---
async def create_db_pool():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, ssl='require')
    async with db_pool.acquire() as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS users (id BIGINT PRIMARY KEY)")
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
                full_name TEXT,
                UNIQUE(test_code, user_id) 
            )
        """) 
        # UNIQUE(test_code, user_id) - Bir odam bir testni 2 marta topshira olmasligi uchun

async def close_db_pool():
    if db_pool: await db_pool.close()

# --- STATES ---
class BotStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_file = State()
    waiting_for_code = State()
    waiting_for_minutes = State()

def generate_code():
    return ''.join(random.choices(string.digits, k=5))

# --- YORDAMCHI FUNKSIYALAR ---
async def show_test_menu(message, test_id):
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT * FROM tests WHERE id = $1", test_id)
    if not test: return
    status = "🟢 Aktiv" if test['is_active'] else "🔴 Deaktiv"
    time_info = ""
    if test['is_active'] and test['end_time']:
        now = datetime.utcnow()
        remaining = test['end_time'] - now
        if remaining.total_seconds() > 0:
            mins = int(remaining.total_seconds() / 60)
            time_info = f"\n⏳ Qoldi: {mins} daqiqa"
        else:
            time_info = "\n⌛️ Vaqt tugagan"

    text = (f"🆔 Kod: <b>{test['unique_code']}</b>\n📝 Nom: {test['name']}\n📊 Holat: {status}{time_info}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Aktivlash" if not test['is_active'] else "🔴 To'xtatish", callback_data=f"toggle_{test_id}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del_{test_id}")],
        [InlineKeyboardButton(text="🔙 Testlarim", callback_data="my_tests")]
    ])
    if isinstance(message, types.CallbackQuery):
        await message.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

# --- HANDLERLAR ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING", message.from_user.id)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✍️ Test Yechish"), KeyboardButton(text="➕ Test Yaratish")],
        [KeyboardButton(text="📂 Mening Testlarim")]
    ], resize_keyboard=True)
    await message.answer(f"Salom {message.from_user.full_name}!", reply_markup=kb)

@dp.message(F.text == "➕ Test Yaratish")
async def create_test_start(message: types.Message, state: FSMContext):
    await message.answer("📝 Test nomini yozing:")
    await state.set_state(BotStates.waiting_for_name)

@dp.message(BotStates.waiting_for_name)
async def create_test_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("📂 HEMIS formatdagi faylni yuklang.", parse_mode="HTML")
    await state.set_state(BotStates.waiting_for_file)

@dp.message(BotStates.waiting_for_file, F.document)
async def create_test_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    file = await bot.get_file(message.document.file_id)
    content = (await bot.download_file(file.file_path)).read().decode('utf-8')
    try:
        json.loads(content)
        final_content = content
    except:
        final_content = parse_hemis_format(content)
        if final_content == "[]":
            await message.answer("❌ Savollar topilmadi.")
            return

    unique_code = generate_code()
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO tests (owner_id, name, unique_code, questions, is_active) VALUES ($1, $2, $3, $4, 0)", 
                           message.from_user.id, data['name'], unique_code, final_content)
    await message.answer(f"✅ Test yuklandi! Kod: <b>{unique_code}</b>", parse_mode="HTML")
    await state.clear()

@dp.message(F.text == "📂 Mening Testlarim")
async def my_tests_list(message: types.Message):
    async with db_pool.acquire() as conn:
        tests = await conn.fetch("SELECT id, name, unique_code, is_active FROM tests WHERE owner_id = $1 ORDER BY id DESC", message.from_user.id)
    if not tests:
        await message.answer("Testlar yo'q.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'🟢' if t['is_active'] else '🔴'} {t['unique_code']} - {t['name']}", callback_data=f"view_{t['id']}")] for t in tests
    ])
    await message.answer("Sizning testlaringiz:", reply_markup=kb)

@dp.callback_query(F.data == "my_tests")
async def back_to_my_tests(call: types.CallbackQuery):
    await call.message.delete(); await my_tests_list(call.message)

@dp.callback_query(F.data.startswith("view_"))
async def view_test_details(call: types.CallbackQuery):
    await show_test_menu(call, int(call.data.split("_")[1]))

@dp.callback_query(F.data.startswith("del_"))
async def delete_test(call: types.CallbackQuery):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM tests WHERE id = $1", int(call.data.split("_")[1]))
    await call.answer("O'chirildi."); await back_to_my_tests(call)

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_test_status(call: types.CallbackQuery, state: FSMContext):
    test_id = int(call.data.split("_")[1])
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT is_active FROM tests WHERE id = $1", test_id)
        if test['is_active']:
            await conn.execute("UPDATE tests SET is_active = 0, end_time = NULL WHERE id = $1", test_id)
            await call.answer("To'xtatildi"); await show_test_menu(call, test_id)
        else:
            await state.update_data(test_id=test_id)
            await call.message.answer("⏱ Necha daqiqa ochiq tursin?")
            await state.set_state(BotStates.waiting_for_minutes)

@dp.message(BotStates.waiting_for_minutes)
async def set_active_minutes(message: types.Message, state: FSMContext):
    try:
        minutes = int(message.text)
        if minutes <= 0: raise ValueError
        data = await state.get_data()
        end_time = datetime.utcnow() + timedelta(minutes=minutes)
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE tests SET is_active = 1, end_time = $1 WHERE id = $2", end_time, data['test_id'])
        await message.answer(f"✅ {minutes} daqiqaga yoqildi!")
        await state.clear()
    except:
        await message.answer("Raqam kiriting.")

# --- TEST YECHISH (Login Logic Update) ---
@dp.message(F.text == "✍️ Test Yechish")
async def solve_test_ask_code(message: types.Message, state: FSMContext):
    await message.answer("🔑 Test kodini kiriting:")
    await state.set_state(BotStates.waiting_for_code)

@dp.message(BotStates.waiting_for_code)
async def check_test_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    user_id = message.from_user.id
    
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT * FROM tests WHERE unique_code = $1", code)
        # Oldin topshirganligini tekshirish
        result = await conn.fetchrow("SELECT id FROM results WHERE test_code = $1 AND user_id = $2", code, user_id)

    if not test:
        await message.answer("❌ Test topilmadi.")
        return
    if result:
        await message.answer("✅ Siz bu testni allaqachon topshirgansiz!")
        return
    if not test['is_active']:
        await message.answer("🚫 Test o'chirilgan.")
        return
    if test['end_time'] and datetime.utcnow() > test['end_time']:
        await message.answer("⌛️ Vaqt tugagan.")
        return

    # User ID ni URL ga qo'shib beramiz
    app_link = f"{WEB_APP_URL}?code={code}&userId={user_id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🚀 Boshlash: {test['name']}", web_app=WebAppInfo(url=app_link))]
    ])
    await message.answer("Testga kirish:", reply_markup=kb)
    await state.clear()

@dp.message(F.web_app_data)
async def handle_webapp_data(message: types.Message):
    data = json.loads(message.web_app_data.data)
    # Bazaga yozamiz
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT owner_id, name FROM tests WHERE unique_code = $1", data['test_code'])
        # ON CONFLICT DO NOTHING - agar qayta yuborsa xato bermasligi uchun
        await conn.execute("""
            INSERT INTO results (test_code, user_id, score, total, full_name) 
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (test_code, user_id) DO NOTHING
        """, data['test_code'], message.from_user.id, data['score'], data['total'], data['student_name'])

    await message.answer(f"✅ Natija qabul qilindi: {data['score']}/{data['total']}")
    if test:
        try:
            await bot.send_message(test['owner_id'], f"🔔 <b>Yechim:</b> {test['name']}\n👤 {data['student_name']}\n📊 {data['score']}/{data['total']}", parse_mode="HTML")
        except: pass

# --- SERVER API (Update) ---
routes = web.RouteTableDef()
@routes.get('/')
async def home(request): return web.Response(text="Running")

@routes.get('/api/get_test')
async def api_get_test(request):
    code = request.query.get('code')
    user_id = request.query.get('userId') # URL dan user_id ni olamiz
    
    if not code or not db_pool: return web.json_response({"error": "Error"}, status=400)
    
    async with db_pool.acquire() as conn:
        # User oldin topshirganmi?
        if user_id:
            res = await conn.fetchrow("SELECT id FROM results WHERE test_code = $1 AND user_id = $2", code, int(user_id))
            if res:
                return web.json_response({"error": "submitted"}) # Allaqachon topshirgan

        row = await conn.fetchrow("SELECT questions, name, end_time FROM tests WHERE unique_code = $1", code)
    
    if row:
        rem_sec = 0
        if row['end_time']:
            delta = row['end_time'] - datetime.utcnow()
            rem_sec = int(delta.total_seconds())
        if rem_sec <= 0: return web.json_response({"error": "expired"})
        
        return web.json_response({
            "name": row['name'], 
            "questions": json.loads(row['questions']),
            "remaining_seconds": rem_sec 
        })
    return web.json_response({"error": "not_found"}, status=404)

async def start_server():
    app = web.Application()
    app.add_routes(routes)
    cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*", allow_methods="*")})
    for route in list(app.router.routes()): cors.add(route)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()

async def main():
    await create_db_pool()
    try: await start_server(); await dp.start_polling(bot)
    finally: await close_db_pool()

if __name__ == "__main__":
    if TOKEN: asyncio.run(main())
