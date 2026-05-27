import os
import sys
import asyncio
import logging
import asyncpg
import traceback
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from openai import AsyncOpenAI

# Отключаем буферизацию вывода
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

print("=== Запуск бота ===")

# Проверяем переменные окружения
required_vars = ["TELEGRAM_TOKEN", "OPENROUTER_API_KEY", "DATABASE_URL"]
for var in required_vars:
    if var not in os.environ:
        print(f"ОШИБКА: переменная {var} не установлена", file=sys.stderr)
        sys.exit(1)
    print(f"{var} установлена (первые 10 символов: {os.environ[var][:10]}...)")

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]

# Клиент OpenRouter (совместим с OpenAI API)
client = AsyncOpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)

# Бот
storage = MemoryStorage()
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=storage)

logging.basicConfig(level=logging.INFO)

# --- Работа с базой данных ---
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id),
            task_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            is_done BOOLEAN DEFAULT FALSE
        );
    """)
    await conn.close()

async def save_user(user_id: int, username: str = None):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        INSERT INTO users (user_id, username) VALUES ($1, $2)
        ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username;
    """, user_id, username)
    await conn.close()

async def add_task_to_db(user_id: int, task_text: str):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        INSERT INTO tasks (user_id, task_text) VALUES ($1, $2);
    """, user_id, task_text)
    await conn.close()
    return "✅ Задача добавлена!"

async def get_tasks_from_db(user_id: int):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("""
        SELECT id, task_text, is_done FROM tasks
        WHERE user_id = $1 AND is_done = FALSE
        ORDER BY created_at DESC;
    """, user_id)
    await conn.close()
    tasks = [f"🔘 {row['task_text']}" for row in rows if not row['is_done']]
    return tasks if tasks else ["🚀 У тебя пока нет задач!"]

async def complete_task_in_db(user_id: int, task_id: int):
    conn = await asyncpg.connect(DATABASE_URL)
    result = await conn.execute("""
        UPDATE tasks SET is_done = TRUE
        WHERE user_id = $1 AND id = $2;
    """, user_id, task_id)
    await conn.close()
    if result == "UPDATE 1":
        return "🎉 Умница! Задача выполнена!"
    else:
        return "😕 Задача с таким номером не найдена."

# --- Обработчики команд ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await save_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "Привет! Я твой личный секретарь.\n"
        "Добавляй задачи командой /add, смотри список /list, отмечай выполненные /done.\n"
        "Можешь просто писать задачи — я их запомню!"
    )

@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    task = message.text.replace("/add", "", 1).strip()
    if not task:
        await message.answer("Напиши задачу после команды, например: `/add Купить хлеб`", parse_mode="MarkdownV2")
        return
    result = await add_task_to_db(message.from_user.id, task)
    await message.answer(result)

@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    tasks = await get_tasks_from_db(message.from_user.id)
    task_list = "\n".join(tasks)
    await message.answer(f"📋 *Твои задачи:*\n{task_list}", parse_mode="MarkdownV2")

@dp.message(Command("done"))
async def cmd_done(message: types.Message):
    try:
        task_id = int(message.text.replace("/done", "", 1).strip())
    except ValueError:
        await message.answer("Укажи номер задачи после команды, например: `/done 1`", parse_mode="MarkdownV2")
        return
    result = await complete_task_in_db(message.from_user.id, task_id)
    await message.answer(result)

@dp.message()
async def handle_ai_query(message: types.Message):
    await save_user(message.from_user.id, message.from_user.username)
    await bot.send_chat_action(message.chat.id, action="typing")
    try:
        # Используем openrouter/free — автоматический выбор лучшей бесплатной модели
        response = await client.chat.completions.create(
            model="openrouter/free",
            messages=[
                {"role": "system", "content": "Ты — полезный и дружелюбный личный ассистент. Помогай пользователю планировать задачи, отвечай на вопросы и поддерживай позитивный настрой."},
                {"role": "user", "content": message.text}
            ],
        )
        reply = response.choices[0].message.content
        await message.answer(reply)
    except Exception as e:
        logging.error(f"Ошибка при запросе к OpenRouter: {e}")
        await message.answer("Извини, произошла ошибка при обращении к нейросети. Попробуй позже.")

# --- Запуск ---
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("FATAL ERROR in asyncio.run:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
