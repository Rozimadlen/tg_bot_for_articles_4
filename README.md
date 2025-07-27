# Telegram Article Adaptation Bot 🤖✍️

Этот бот автоматически адаптирует статьи под 5 платформ: VC.ru, Дзен, TenChat, VK и Telegram, используя DeepSeek API.

## 🚀 Как запустить на Render (бесплатно):

1. Сделай форк этого репозитория или залей свой.
2. Зайди на [https://render.com](https://render.com) → New → Web Service.
3. Подключи GitHub репозиторий.
4. Введи переменные окружения:
   - `TG_BOT_TOKEN`
   - `OPENROUTER_API_KEY`
5. В `Start Command` не указывай ничего — Render сам подхватит `Procfile`.
6. Жми **Deploy**.

## 📎 Пример команды для запуска локально:
```bash
python3 bot.py
```

## 📦 Зависимости:
- Aiogram 3
- Aiohttp
- dotenv
- DeepSeek API
