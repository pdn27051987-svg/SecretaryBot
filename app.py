# app.py для Cloudflare Workers
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Update
from openai import AsyncOpenAI
import json
import os
import asyncpg
import logging

# --- Настройки из переменных окружения (будут на Cloudflare) ---
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

# --- Инициализация бота и клиентов ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)

# --- Обработчики команд (ваши старые функции, они не меняются) ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я твой личный секретарь (теперь на Cloudflare Workers!).\n"
                         "Добавляй задачи командой /add, смотри список /list, отмечай выполненные /done.\n"
                         "Можешь просто писать задачи — я их запомню!")

@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    task = message.text.replace("/add", "", 1).strip()
    if not task:
        await message.answer("Напиши задачу после команды, например: `/add Купить хлеб`", parse_mode="MarkdownV2")
        return
    # Здесь будет ваша логика добавления задачи в базу данных
    await message.answer(f"✅ Задача '{task}' добавлена!")

@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    # Здесь будет ваша логика получения списка задач
    await message.answer(f"📋 *Твои задачи:*\nПока здесь пусто", parse_mode="MarkdownV2")

@dp.message(Command("done"))
async def cmd_done(message: types.Message):
    # Здесь будет ваша логика отметки задачи выполненной
    await message.answer("🎉 Умница! Задача выполнена!")

@dp.message()
async def handle_ai_query(message: types.Message):
    await bot.send_chat_action(message.chat.id, action="typing")
    try:
        response = await client.chat.completions.create(
            model="google/gemini-2.0-flash-lite-preview-02-05:free",
            messages=[
                {"role": "system", "content": "Ты — полезный, дружелюбный и адекватный личный ассистент. Отвечай кратко и по делу."},
                {"role": "user", "content": message.text}
            ],
        )
        reply = response.choices[0].message.content
        await message.answer(reply)
    except Exception as e:
        logging.error(f"Ошибка при запросе к Gemini: {e}")
        await message.answer("Извини, произошла ошибка. Попробуй позже.")

# --- Точка входа для Cloudflare Workers ---
async def fetch(request):
    # Извлекаем тело запроса, которое Telegram присылает как JSON
    update = Update(**await request.json())
    # Передаём обновление в диспетчер aiogram
    await dp.feed_update(bot, update)
    # Возвращаем успешный ответ для Telegram
    return web.Response(text="OK")

# Это нужно для локального тестирования, но на Cloudflare не используется
if __name__ == "__main__":
    print("Этот файл предназначен для Cloudflare Workers. Запустите его там.")
