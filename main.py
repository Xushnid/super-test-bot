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

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEB_APP_URL = "https://xushnid.github.io/super-test-bot/" 

bot = Bot(token=TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)
db_pool = None

# --- HEMIS PARSER ---
def parse_hemis_format(text):
    questions = []
    blocks = text.replace('\r\n', '\n').split('+++++')
    for block in blocks:
        block = block.strip()
        if not block: continue
        parts = block.split('====')
        if len(parts) < 2: continue
        q_text = parts[0].strip()
        answers = []
        correct_index = -1
        answer_parts = parts[1:]
        valid_answers = []
        for ans in answer_parts:
            ans = ans.strip()
            if not ans: continue
            if ans.startswith('#'):
                correct_index = len(valid_answers)
                ans = ans[1:].strip()
            valid_answers.append(ans)
        if q_text and valid_answers and correct_index != -1:
            questions.append({"q": q_text, "a": valid_answers, "c": correct_index})
    return json.dumps(questions)

# --- BAZA ---
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
                end_time TIMESTAMP,
                session_version INTEGER DEFAULT 1,
                last_stats_msg_id INTEGER DEFAULT 0
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
                session_version INTEGER DEFAULT 1,
                UNIQUE(test_code, user_id)
            )
        """)

async def close_db_pool():
    if db_pool: await db_pool.close()

# --- STATES ---
class BotStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_file = State()
    waiting_for_code = State()
    waiting_for_minutes = State()

def generate_code(): return ''.join(random.choices(string.digits, k=5))

# --- BOT HANDLERLARI ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING", message.from_user.id)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✍️ Test Yechish"), KeyboardButton(text="➕ Test Yaratish")],
        [KeyboardButton(text="📂 Mening Testlarim")]
    ], resize_keyboard=True)
    await message.answer(f"Salom {message.from_user.full_name}!", reply_markup=kb)

# ... (Test yaratish va Mening testlarim qismi o'zgarmadi, joy tejash uchun qisqartirib yozaman, siz eskisi kabi qoldiring) ...
# Faqat eng muhim o'zgarishlar pastda API qismida

@dp.message(F.text == "➕ Test Yaratish")
async def create_test_start(message: types.Message, state: FSMContext):
    await message.answer("📝 Test nomi:")
    await state.set_state(BotStates.waiting_for_name)

@dp.message(BotStates.waiting_for_name)
async def create_test_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("📂 HEMIS faylni yuklang.")
    await state.set_state(BotStates.waiting_for_file)

@dp.message(BotStates.waiting_for_file, F.document)
async def create_test_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    file = await bot.get_file(message.document.file_id)
    content = (await bot.download_file(file.file_path)).read().decode('utf-8')
    final_content = parse_hemis_format(content)
    if final_content == "[]":
        await message.answer("❌ Savollar topilmadi.")
        return
    unique_code = generate_code()
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO tests (owner_id, name, unique_code, questions, is_active) VALUES ($1, $2, $3, $4, 0)", 
                           message.from_user.id, data['name'], unique_code, final_content)
    await message.answer(f"✅ Kod: <b>{unique_code}</b>", parse_mode="HTML")
    await state.clear()

@dp.message(F.text == "📂 Mening Testlarim")
async def my_tests_list(message: types.Message):
    async with db_pool.acquire() as conn:
        tests = await conn.fetch("SELECT id, name, unique_code, is_active FROM tests WHERE owner_id = $1 ORDER BY id DESC", message.from_user.id)
    if not tests: return await message.answer("Testlar yo'q.")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'🟢' if t['is_active'] else '🔴'} {t['unique_code']} - {t['name']}", callback_data=f"view_{t['id']}")] for t in tests
    ])
    await message.answer("Testlaringiz:", reply_markup=kb)

@dp.callback_query(F.data == "my_tests")
async def back_to_my_tests(call: types.CallbackQuery):
    await call.message.delete(); await my_tests_list(call.message)

@dp.callback_query(F.data.startswith("view_"))
async def view_test_details(call: types.CallbackQuery):
    test_id = int(call.data.split("_")[1])
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT * FROM tests WHERE id = $1", test_id)
    if not test: return
    status = "🟢 Aktiv" if test['is_active'] else "🔴 Deaktiv"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Aktivlash" if not test['is_active'] else "🔴 To'xtatish", callback_data=f"toggle_{test_id}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del_{test_id}")],
        [InlineKeyboardButton(text="📊 Natijalar", callback_data=f"stats_{test_id}")]
    ])
    await call.message.edit_text(f"🆔 Kod: <b>{test['unique_code']}</b>\n📝 Nom: {test['name']}\n📊 Holat: {status}", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("del_"))
async def delete_test(call: types.CallbackQuery):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM tests WHERE id = $1", int(call.data.split("_")[1]))
    await call.answer("O'chirildi."); await call.message.delete()

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_test_status(call: types.CallbackQuery, state: FSMContext):
    test_id = int(call.data.split("_")[1])
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT is_active, session_version FROM tests WHERE id = $1", test_id)
        if test['is_active']:
            await conn.execute("UPDATE tests SET is_active = 0, end_time = NULL WHERE id = $1", test_id)
            await call.answer("To'xtatildi")
            # Qaytadan view qilish (xato bermasligi uchun try except)
            try: await view_test_details(call) 
            except: pass
        else:
            new_version = test['session_version'] + 1
            await conn.execute("UPDATE tests SET session_version = $1 WHERE id = $2", new_version, test_id)
            await state.update_data(test_id=test_id)
            await call.message.answer("⏱ Necha daqiqa?")
            await state.set_state(BotStates.waiting_for_minutes)

@dp.message(BotStates.waiting_for_minutes)
async def set_active_minutes(message: types.Message, state: FSMContext):
    try:
        minutes = int(message.text)
        data = await state.get_data()
        end_time = datetime.utcnow() + timedelta(minutes=minutes)
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE tests SET is_active = 1, end_time = $1, last_stats_msg_id = 0 WHERE id = $2", end_time, data['test_id'])
        await message.answer(f"✅ {minutes} daqiqaga yoqildi!")
        await state.clear()
    except:
        await message.answer("Raqam kiriting.")

# --- LOGIN ---
@dp.message(F.text == "✍️ Test Yechish")
async def solve_test_ask_code(message: types.Message, state: FSMContext):
    await message.answer("🔑 Test kodi:")
    await state.set_state(BotStates.waiting_for_code)

@dp.message(BotStates.waiting_for_code)
async def check_test_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    user_id = message.from_user.id
    
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT * FROM tests WHERE unique_code = $1", code)
        result = await conn.fetchrow("SELECT session_version FROM results WHERE test_code = $1 AND user_id = $2", code, user_id)

    if not test: return await message.answer("❌ Test topilmadi.")
    if not test['is_active']: return await message.answer("🚫 Test o'chirilgan.")
    if result and result['session_version'] >= test['session_version']:
        return await message.answer("✅ Bu sessiyada topshirib bo'lgansiz.")
    if test['end_time'] and datetime.utcnow() > test['end_time']:
        return await message.answer("⌛️ Vaqt tugagan.")

    app_link = f"{WEB_APP_URL}?code={code}&userId={user_id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🚀 Boshlash", web_app=WebAppInfo(url=app_link))]])
    await message.answer("Testga kirish:", reply_markup=kb)
    await state.clear()

# =======================================================
# YANGI API QISMI (ENG MUHIMI)
# =======================================================
routes = web.RouteTableDef()

@routes.get('/')
async def home(request): return web.Response(text="Running")

@routes.get('/api/get_test')
async def api_get_test(request):
    code = request.query.get('code')
    user_id = request.query.get('userId')
    if not code or not db_pool: return web.json_response({"error": "Error"}, status=400)
    
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT questions, name, end_time, session_version FROM tests WHERE unique_code = $1", code)
        if not test: return web.json_response({"error": "not_found"}, status=404)
        
        if user_id:
            res = await conn.fetchrow("SELECT session_version FROM results WHERE test_code = $1 AND user_id = $2", code, int(user_id))
            if res and res['session_version'] >= test['session_version']:
                 return web.json_response({"error": "submitted"})

        rem_sec = 0
        if test['end_time']:
            rem_sec = int((test['end_time'] - datetime.utcnow()).total_seconds())
        if rem_sec <= 0: return web.json_response({"error": "expired"})
        
        return web.json_response({
            "name": test['name'], 
            "questions": json.loads(test['questions']),
            "remaining_seconds": rem_sec 
        })

# --- YANGI POST METHOD (Telegram sendData o'rniga) ---
@routes.post('/api/submit_result')
async def api_submit_result(request):
    try:
        data = await request.json()
        # data: {test_code, userId, student_name, score, total}
        
        test_code = data.get('test_code')
        user_id = int(data.get('userId'))
        student_name = data.get('student_name')
        score = int(data.get('score'))
        total = int(data.get('total'))

        async with db_pool.acquire() as conn:
            test = await conn.fetchrow("SELECT owner_id, name, session_version, last_stats_msg_id, id FROM tests WHERE unique_code = $1", test_code)
            if not test: return web.json_response({"error": "Test not found"}, status=404)

            # Bazaga yozish
            await conn.execute("""
                INSERT INTO results (test_code, user_id, score, total, full_name, session_version) 
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (test_code, user_id) 
                DO UPDATE SET score = $3, total = $4, full_name = $5, session_version = $6
            """, test_code, user_id, score, total, student_name, test['session_version'])

            # Talabaga botdan xabar yuborish
            try:
                await bot.send_message(user_id, f"✅ <b>Natija qabul qilindi!</b>\n📚 {test['name']}\n📊 {score}/{total}", parse_mode="HTML")
            except Exception as e:
                print(f"Talabaga yuborilmadi: {e}")

            # TEST EGASIGA YANGILANADIGAN XABAR
            all_results = await conn.fetch("""
                SELECT full_name, score, total FROM results 
                WHERE test_code = $1 AND session_version = $2 
                ORDER BY score DESC
            """, test_code, test['session_version'])
            
            stats_text = f"📊 <b>Natijalar: {test['name']}</b>\n\n"
            for i, res in enumerate(all_results, 1):
                stats_text += f"{i}. {res['full_name']} — <b>{res['score']}/{res['total']}</b>\n"
            
            msg_id = test['last_stats_msg_id']
            try:
                if msg_id > 0:
                    await bot.edit_message_text(chat_id=test['owner_id'], message_id=msg_id, text=stats_text, parse_mode="HTML")
                else:
                    raise Exception("No msg")
            except:
                try:
                    sent = await bot.send_message(chat_id=test['owner_id'], text=stats_text, parse_mode="HTML")
                    await conn.execute("UPDATE tests SET last_stats_msg_id = $1 WHERE id = $2", sent.message_id, test['id'])
                except: pass

        return web.json_response({"status": "ok"})
    except Exception as e:
        print(f"API Error: {e}")
        return web.json_response({"error": str(e)}, status=500)

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
