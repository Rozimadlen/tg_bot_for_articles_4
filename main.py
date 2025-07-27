import os
import sys
import asyncio
import json
import aiohttp
import re
import html
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

load_dotenv()

# Проверка на SSL
try:
    import ssl
except ModuleNotFoundError:
    print("Ошибка: модуль ssl не найден. Убедитесь, что ваш Python установлен с поддержкой SSL.")
    sys.exit(1)

API_TOKEN = os.getenv("TG_BOT_TOKEN") or "7856435808:AAEAw0m684uJyrX3oX4lWO2n6jEHBs1xSy4"
GPT_API_KEY = os.getenv("OPENROUTER_API_KEY") or "sk-afe1b6ce8f5e4fc8b397fd1c2f47c983"

session = AiohttpSession()
bot = Bot(token=API_TOKEN, session=session)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

platforms = ["VC.ru", "Дзен", "TenChat", "Telegram", "VK"]
multi_part_platforms = {"VC.ru": 3, "Дзен": 3}
user_articles = {}
user_modes = {}
edit_state = {}  # user_id: (index, platform)

@router.message(F.text == "/режим")
async def choose_mode(message: types.Message):
    buttons = [
        [InlineKeyboardButton(text="✏️ Адаптируй мой текст", callback_data="mode_adapt")],
        [InlineKeyboardButton(text="➕ Дополни мой текст", callback_data="mode_extend")],
        [InlineKeyboardButton(text="🆕 Напиши с нуля", callback_data="mode_new")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Выбери режим генерации:", reply_markup=markup)

@router.callback_query(F.data.startswith("mode_"))
async def set_mode(call: CallbackQuery):
    mode = call.data.split("_")[1]
    user_modes[call.from_user.id] = mode
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(f"Режим установлен: {mode}. Пришли текст в формате:\n\nЗаголовок: ...\n\nТекст: ...")

async def generate_structured_adaptation(title, text, platform, mode, memory=None):
    headers = {
        "Authorization": f"Bearer {GPT_API_KEY}",
        "Content-Type": "application/json"
    }

    url = "https://api.deepseek.com/chat/completions"
    model = "deepseek-chat"
    result = ""
    memory = memory or ""

    if platform in multi_part_platforms:
        last_part = ""
        for i in range(1, multi_part_platforms[platform] + 1):
            prompt = f"Ты — автор Telegram-канала @prod_roz. Платформа: {platform}. Режим: {mode}.\n"
            prompt += "Пиши эмоционально, глубоко, с самоиронией. В этой части продолжай предыдущую мысль.\n"
            if i > 1:
                prompt += f"В предыдущей части ты уже писал: {last_part[:400]}...\n"
            prompt += f"ЧАСТЬ {i} из {multi_part_platforms[platform]}.\nЗаголовок: {title}\nИсходный текст: {text}"

            body = {
                "model": model,
                "messages": [{"role": "system", "content": prompt}],
                "temperature": 0.8,
                "max_tokens": 2048
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=body) as resp:
                    if resp.status != 200:
                        return f"❌ Ошибка {resp.status}: {await resp.text()}"
                    data = await resp.json()
                    part = data["choices"][0]["message"]["content"]
                    last_part = part.strip()
                    result += last_part + "\n\n"
    else:
        prompt = (
            f"Ты — автор Telegram-канала @prod_roz. Режим: {mode}. Платформа: {platform}.\n"
            f"Создай законченную адаптацию, с заголовком и логичным завершением.\n"
            f"Заголовок: {title}\nИсходный текст: {text}"
        )
        body = {
            "model": model,
            "messages": [{"role": "system", "content": prompt}],
            "temperature": 0.8,
            "max_tokens": 2048
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body) as resp:
                if resp.status != 200:
                    return f"❌ Ошибка {resp.status}: {await resp.text()}"
                data = await resp.json()
                result = data["choices"][0]["message"]["content"]

    return result.strip()

@router.message(F.text.startswith("/start"))
async def start_handler(message: types.Message):
    await message.answer("Привет! Пришли мне статью в формате:\n\nЗаголовок: ...\n\nТекст: ...")

@router.message(F.text)
async def article_handler(message: types.Message):
    try:
        if message.from_user.id in edit_state:
            index, platform = edit_state.pop(message.from_user.id)
            user_articles[message.from_user.id]["adaptations"][index] = (platform, message.text)
            await message.answer("✏️ Исправление сохранено. Продолжаем просмотр.")
            await send_adaptation(message.chat.id, message.from_user.id)
            return

        match = re.search(r"Заголовок:\s*(.*?)\n+Текст:\s*(.+)", message.text, re.DOTALL)
        if not match:
            await message.answer("⛔ Неверный формат. Используй: Заголовок: ...\n\nТекст: ...")
            return

        title, content = match.groups()
        await message.answer("✍️ Генерирую адаптации по платформам...")

        user_articles[message.from_user.id] = {
            "adaptations": [],
            "approved": [],
            "current": 0
        }
        mode = user_modes.get(message.from_user.id, "adapt")

        for platform in platforms:
            adapted = await generate_structured_adaptation(title, content, platform, mode)
            user_articles[message.from_user.id]["adaptations"].append((platform, adapted))

        await send_adaptation(message.chat.id, message.from_user.id)

    except Exception as e:
        await message.answer("Что-то пошло не так. Ошибка: " + str(e))

async def send_adaptation(chat_id, user_id):
    data = user_articles.get(user_id)
    if not data or data["current"] >= len(data["adaptations"]):
        approved = data.get("approved", [])
        if approved:
            buttons = [[InlineKeyboardButton(text="🚀 Опубликовать выбранные", callback_data="publish_all")],
                       [InlineKeyboardButton(text="🔁 Перечитать", callback_data="restart")]]
            markup = InlineKeyboardMarkup(inline_keyboard=buttons)
            await bot.send_message(chat_id, f"Вы выбрали адаптации для публикации в: {', '.join(approved)}", reply_markup=markup)
        else:
            await bot.send_message(chat_id, "⏭ Все адаптации просмотрены и пропущены.")
        return

    index = data["current"]
    platform, text = data["adaptations"][index]
    safe_text = html.escape(text)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить к публикации", callback_data="add_publish")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip")],
        [InlineKeyboardButton(text="📝 Редактировать", callback_data="edit")]
    ])

    chunk_size = 3500
    chunks = [safe_text[i:i + chunk_size] for i in range(0, len(safe_text), chunk_size)]
    for idx, chunk in enumerate(chunks):
        if idx == len(chunks) - 1:
            await bot.send_message(chat_id, f"🔹 Адаптация для {platform}:\n\n{chunk}", parse_mode="HTML", reply_markup=keyboard)
        else:
            await bot.send_message(chat_id, chunk, parse_mode="HTML")

@router.callback_query(F.data == "add_publish")
async def add_platform(call: CallbackQuery):
    user_id = call.from_user.id
    user_articles[user_id]["approved"].append(user_articles[user_id]["adaptations"][user_articles[user_id]["current"]][0])
    user_articles[user_id]["current"] += 1
    await call.message.edit_reply_markup(reply_markup=None)
    await send_adaptation(call.message.chat.id, user_id)

@router.callback_query(F.data == "skip")
async def skip_platform(call: CallbackQuery):
    user_articles[call.from_user.id]["current"] += 1
    await call.message.edit_reply_markup(reply_markup=None)
    await send_adaptation(call.message.chat.id, call.from_user.id)

@router.callback_query(F.data == "edit")
async def edit_adaptation(call: CallbackQuery):
    user_id = call.from_user.id
    index = user_articles[user_id]["current"]
    platform = user_articles[user_id]["adaptations"][index][0]
    edit_state[user_id] = (index, platform)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer("📝 Пришли исправленный текст.")

@router.callback_query(F.data == "publish_all")
async def publish_selected(call: CallbackQuery):
    approved = user_articles[call.from_user.id].get("approved", [])
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer("📡 Публикация будет реализована позже. Вы выбрали: " + ", ".join(approved))

@router.callback_query(F.data == "restart")
async def restart_adaptations(call: CallbackQuery):
    user_articles[call.from_user.id]["current"] = 0
    user_articles[call.from_user.id]["approved"] = []
    await call.message.edit_reply_markup(reply_markup=None)
    await send_adaptation(call.message.chat.id, call.from_user.id)

async def main():
    import logging
    import nest_asyncio
    nest_asyncio.apply()
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())
