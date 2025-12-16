import asyncio
import json
import logging
import os
import random
import string
from datetime import datetime, timedelta
import asyncpg
import pandas as pd
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
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
                last_stats_msg_id INTEGER DEFAULT 0,
                question_count INTEGER DEFAULT 0
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id SERIAL PRIMARY KEY,
                test_code TEXT,
                user_id BIGINT,
                score INTEGER DEFAULT -1,
                total INTEGER DEFAULT 0,
                full_name TEXT,
                student_msg_id INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(test_code, user_id)
            )
        """)

async def close_db_pool():
    if db_pool: await db_pool.close()

class BotStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_file = State()
    waiting_for_code = State()
    waiting_for_minutes = State()
    waiting_for_count = State()

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
    if final_content == "[]": return await message.answer("❌ Savollar topilmadi.")
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
    q_len = len(json.loads(test['questions']))
    count_info = f"{test['question_count']} ta (Random)" if test['question_count'] > 0 else f"{q_len} ta (Barchasi)"
    
    async with db_pool.acquire() as conn:
        res_count = await conn.fetchval("SELECT COUNT(*) FROM results WHERE test_code = $1 AND score > -1", test['unique_code'])

    text = (f"🆔 Kod: <b>{test['unique_code']}</b>\n📝 Nom: {test['name']}\n📊 Holat: {status}\n❓ Savollar: {count_info}\n👥 Yechganlar: {res_count} ta")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Aktivlash" if not test['is_active'] else "🔴 To'xtatish", callback_data=f"toggle_{test_id}")],
        [InlineKeyboardButton(text="📥 Excel Natijalar", callback_data=f"excel_{test_id}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del_{test_id}")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="my_tests")]
    ])
    try: await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except: await call.message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("del_"))
async def delete_test(call: types.CallbackQuery):
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT unique_code FROM tests WHERE id = $1", int(call.data.split("_")[1]))
        if test:
            await conn.execute("DELETE FROM results WHERE test_code = $1", test['unique_code'])
            await conn.execute("DELETE FROM tests WHERE unique_code = $1", test['unique_code'])
    await call.answer("O'chirildi."); await back_to_my_tests(call)

@dp.callback_query(F.data.startswith("excel_"))
async def send_test_stats_excel(call: types.CallbackQuery):
    test_id = int(call.data.split("_")[1])
    await call.answer("Excel tayyorlanmoqda...")
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT unique_code, name FROM tests WHERE id = $1", test_id)
        results = await conn.fetch("SELECT full_name, score, total, created_at FROM results WHERE test_code = $1 AND score > -1 ORDER BY score DESC", test['unique_code'])
    if not results: return await call.message.answer("❌ Natijalar yo'q.")
    
    data = []
    for res in results:
        local_time = res['created_at'] + timedelta(hours=5)
        data.append({
            "F.I.SH": res['full_name'], "To'g'ri": res['score'], "Jami": res['total'],
            "Foiz": f"{round((res['score']/res['total'])*100)}%", "Vaqt": local_time.strftime("%Y-%m-%d %H:%M")
        })
    df = pd.DataFrame(data)
    filename = f"Natijalar_{test['unique_code']}.xlsx"
    df.to_excel(filename, index=False)
    await call.message.answer_document(FSInputFile(filename), caption=f"📊 <b>{test['name']}</b>")
    os.remove(filename)

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_test_status(call: types.CallbackQuery, state: FSMContext):
    test_id = int(call.data.split("_")[1])
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT is_active, unique_code, questions FROM tests WHERE id = $1", test_id)
        if test['is_active']:
            await conn.execute("UPDATE tests SET is_active = 0, end_time = NULL WHERE id = $1", test_id)
            await call.answer("To'xtatildi"); await view_test_details(call)
        else:
            await conn.execute("DELETE FROM results WHERE test_code = $1", test['unique_code'])
            await state.update_data(test_id=test_id, total_q=len(json.loads(test['questions'])))
            await call.message.answer("🗑 Reset qilindi.\n⏱ Necha daqiqa?")
            await state.set_state(BotStates.waiting_for_minutes)

@dp.message(BotStates.waiting_for_minutes)
async def set_active_minutes(message: types.Message, state: FSMContext):
    try:
        minutes = int(message.text)
        await state.update_data(minutes=minutes)
        data = await state.get_data()
        await message.answer(f"❓ Jami <b>{data['total_q']}</b> ta. Nechtasi random tushsin?", parse_mode="HTML")
        await state.set_state(BotStates.waiting_for_count)
    except: await message.answer("Raqam kiriting.")

@dp.message(BotStates.waiting_for_count)
async def set_active_count(message: types.Message, state: FSMContext):
    try:
        count = int(message.text)
        data = await state.get_data()
        if count > data['total_q']: return await message.answer(f"❌ Maksimal: {data['total_q']}")
        end_time = datetime.utcnow() + timedelta(minutes=data['minutes'])
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE tests SET is_active = 1, end_time = $1, question_count = $2, last_stats_msg_id = 0 WHERE id = $3", end_time, count, data['test_id'])
        await message.answer(f"✅ Yoqildi! {data['minutes']} daqiqa, {count} ta savol.")
        await state.clear()
    except: await message.answer("Raqam kiriting.")

@dp.message(F.text == "✍️ Test Yechish")
async def solve_test_ask_code(message: types.Message, state: FSMContext):
    await message.answer("🔑 Kod:")
    await state.set_state(BotStates.waiting_for_code)

@dp.message(BotStates.waiting_for_code)
async def check_test_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    user_id = message.from_user.id
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT * FROM tests WHERE unique_code = $1", code)
        result = await conn.fetchrow("SELECT score FROM results WHERE test_code = $1 AND user_id = $2", code, user_id)

    if not test: return await message.answer("❌ Test topilmadi.")
    if not test['is_active']: return await message.answer("🚫 Deaktiv.")
    
    # MUHIM: Bu yerda endi bloklamaymiz, WebApp o'zi hal qiladi (reload uchun kerak)
    # Faqat vaqtni tekshiramiz
    if test['end_time'] and datetime.utcnow() > test['end_time']: return await message.answer("⌛️ Vaqt tugagan.")

    app_link = f"{WEB_APP_URL}?code={code}&userId={user_id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🚀 Boshlash: {test['name']}", web_app=WebAppInfo(url=app_link))]])
    
    # Message ID saqlaymiz
    sent_msg = await message.answer(f"Testga marhamat!", reply_markup=kb)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO results (test_code, user_id, full_name, student_msg_id, score)
            VALUES ($1, $2, $3, $4, -1)
            ON CONFLICT (test_code, user_id) 
            DO UPDATE SET student_msg_id = $4, full_name = $3
        """, code, user_id, message.from_user.full_name, sent_msg.message_id)
    await state.clear()

# --- API ---
routes = web.RouteTableDef()
@routes.get('/')
async def home(request): return web.Response(text="Running")

@routes.get('/api/get_test')
async def api_get_test(request):
    code = request.query.get('code')
    user_id = request.query.get('userId')
    if not code or not db_pool: return web.json_response({"error": "Error"}, status=400)
    
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT * FROM tests WHERE unique_code = $1", code)
        if not test: return web.json_response({"error": "not_found"}, status=404)
        
        # --- RELOAD LOGIKASI ---
        if user_id:
            res = await conn.fetchrow("SELECT score, total FROM results WHERE test_code = $1 AND user_id = $2", code, int(user_id))
            # Agar ball -1 dan katta bo'lsa, demak topshirib bo'lgan -> Natijani qaytaramiz
            if res and res['score'] > -1:
                 return web.json_response({
                     "status": "finished",
                     "score": res['score'],
                     "total": res['total'],
                     "name": test['name']
                 })

        rem_sec = 0
        if test['end_time']:
            rem_sec = int((test['end_time'] - datetime.utcnow()).total_seconds())
        if rem_sec <= 0: return web.json_response({"error": "expired"})
        
        # RANDOM
        all_questions = json.loads(test['questions'])
        count = test['question_count']
        seed_val = f"{user_id}_{test['unique_code']}"
        random.seed(seed_val)
        selected_questions = random.sample(all_questions, count) if 0 < count < len(all_questions) else all_questions

        return web.json_response({
            "status": "active",
            "name": test['name'], 
            "questions": selected_questions,
            "remaining_seconds": rem_sec 
        })

@routes.post('/api/submit_result')
async def api_submit_result(request):
    try:
        data = await request.json()
        test_code = data.get('test_code')
        user_id = int(data.get('userId'))
        student_name = data.get('student_name')
        score = int(data.get('score'))
        total = int(data.get('total'))

        async with db_pool.acquire() as conn:
            test = await conn.fetchrow("SELECT * FROM tests WHERE unique_code = $1", test_code)
            if not test: return web.json_response({"error": "Not found"}, status=404)

            # Bazaga yozish
            await conn.execute("""
                INSERT INTO results (test_code, user_id, score, total, full_name) 
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (test_code, user_id) 
                DO UPDATE SET score = $3, total = $4, full_name = $5
            """, test_code, user_id, score, total, student_name)

            # Talabaga xabar
            res_row = await conn.fetchrow("SELECT student_msg_id FROM results WHERE test_code=$1 AND user_id=$2", test_code, user_id)
            if res_row and res_row['student_msg_id']:
                try:
                    await bot.edit_message_text(chat_id=user_id, message_id=res_row['student_msg_id'],
                        text=f"🏁 <b>Test yakunlandi!</b>\n\n📚 {test['name']}\n✅ Natija: <b>{score} / {total}</b>", parse_mode="HTML")
                except: pass

            # Egasiga statistika
            all_results = await conn.fetch("SELECT full_name, score, total FROM results WHERE test_code = $1 AND score > -1 ORDER BY score DESC", test_code)
            stats_text = f"📊 <b>Natijalar (Guruh): {test['name']}</b>\n\n"
            for i, res in enumerate(all_results, 1):
                stats_text += f"{i}. {res['full_name']} — <b>{res['score']}/{res['total']}</b>\n"
            
            msg_id = test['last_stats_msg_id']
            try:
                if msg_id > 0: await bot.edit_message_text(chat_id=test['owner_id'], message_id=msg_id, text=stats_text, parse_mode="HTML")
                else: raise Exception
            except:
                try:
                    sent = await bot.send_message(chat_id=test['owner_id'], text=stats_text, parse_mode="HTML")
                    await conn.execute("UPDATE tests SET last_stats_msg_id = $1 WHERE id = $2", sent.message_id, test['id'])
                except: pass

        return web.json_response({"status": "ok"})
    except Exception as e:
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
