import os
import json
import re
import asyncio
import requests
import random
from datetime import datetime, date, timedelta

from openai import OpenAI
import edge_tts

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes, CallbackQueryHandler

# ======== ТОКЕНЫ ========
TELEGRAM_BOT_TOKEN = "8434163956:AAFsId_CNRX2rkCBH4_gsIrWxa99k1ohUsA"
OPENAI_API_KEY = "sk-5172653204024fcaa7e26de04f04ec47"

# ======== ОПЛАТА И РЕКВИЗИТЫ ========
CARD_NUMBER = "2202208186522703"
DONATE_LINK = "2202208186522703"
MONTHLY_PRICE = "299 рублей"
YEARLY_PRICE = "1990 рублей"

# Твой личный Telegram ID
ADMIN_ID = "1177629279"

# ======== ИНИЦИАЛИЗАЦИЯ DEEPSEEK ========
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://api.deepseek.com"
)

# ======== БАЗА ДАННЫХ (JSON) ========
DB_FILE = "stories.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"stories": [], "premium_users": {}, "user_stats": {}, "pending_payments": {}, "payment_requests": {}}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"stories": [], "premium_users": {}, "user_stats": {}, "pending_payments": {}, "payment_requests": {}}

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

def save_story(user_id, name, topic, length, moral, language, trait, appearance, story_text):
    db = load_db()
    db["stories"].append({
        "id": len(db["stories"]) + 1,
        "user_id": user_id,
        "name": name,
        "topic": topic,
        "length": length,
        "moral": moral,
        "language": language,
        "trait": trait,
        "appearance": appearance,
        "story_text": story_text,
        "created_at": datetime.now().isoformat()
    })
    save_db(db)

def get_user_stories(user_id):
    db = load_db()
    return [s for s in db["stories"] if s["user_id"] == user_id][::-1]

def delete_story(story_id, user_id):
    db = load_db()
    db["stories"] = [s for s in db["stories"] if not (s["id"] == story_id and s["user_id"] == user_id)]
    save_db(db)

# ======== ФУНКЦИИ ПОДПИСКИ ========
def is_premium(user_id):
    db = load_db()
    if str(user_id) not in db["premium_users"]:
        return False
    expiration = db["premium_users"][str(user_id)]["expiration"]
    return datetime.now() < datetime.fromisoformat(expiration)

def get_user_story_count(user_id):
    db = load_db()
    count = 0
    for s in db["stories"]:
        if s["user_id"] == user_id:
            count += 1
    return count

def increment_daily_count(user_id):
    db = load_db()
    if str(user_id) not in db["user_stats"]:
        db["user_stats"][str(user_id)] = {"daily_count": 0, "last_reset": date.today().isoformat()}
    db["user_stats"][str(user_id)]["daily_count"] += 1
    save_db(db)

def can_create_story(user_id):
    if is_premium(user_id):
        return True
    return get_user_story_count(user_id) < 3

def activate_subscription(user_id, days):
    db = load_db()
    expiration = datetime.now() + timedelta(days=days)
    db["premium_users"][str(user_id)] = {"expiration": expiration.isoformat()}
    save_db(db)
def get_payment_keyboard():
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить месяц (299 руб.)", callback_data="pay_month")],
        [InlineKeyboardButton("💳 Оплатить год (1990 руб.)", callback_data="pay_year")],
    ]
    return InlineKeyboardMarkup(keyboard)
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📖 Создать сказку")],
        [KeyboardButton("🎲 Удиви меня")],
        [KeyboardButton("📚 Мои сказки")],
        [KeyboardButton("❤️ Поддержать автора")],
        [KeyboardButton("❓ Помощь")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_payment_keyboard():
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить месяц (299 руб.)", callback_data="pay_month")],
        [InlineKeyboardButton("💳 Оплатить год (1990 руб.)", callback_data="pay_year")],
    ]
    return InlineKeyboardMarkup(keyboard)
def get_admin_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"confirm_{user_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)
def get_admin_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"confirm_{user_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_topic_keyboard():
    return ReplyKeyboardMarkup([
        ["🚀 Космос"],
        ["🦕 Динозавры"],
        ["👸 Принцессы"],
        ["🏴‍☠️ Пираты"],
        ["🧚 Феи и Волшебство"],
        ["🐾 Лесные зверята"],
        ["🎄 Новый год и Зима"],
        ["🏰 Рыцари и Замки"],
        ["🌊 Подводный мир"],
    ], one_time_keyboard=True, resize_keyboard=True)

def get_moral_keyboard():
    return ReplyKeyboardMarkup([
        ["💛 Дружба"],
        ["🏆 Смелость"],
        ["🤝 Доброта"],
        ["🔍 Честность"],
        ["🏡 Семья"],
        ["🔬 Любознательность"],
        ["🎭 Терпение"],
    ], one_time_keyboard=True, resize_keyboard=True)

def get_language_keyboard():
    return ReplyKeyboardMarkup([["🇷🇺 Русский"]], one_time_keyboard=True, resize_keyboard=True)

def get_trait_keyboard():
    return ReplyKeyboardMarkup([[trait] for trait in CHARACTER_TRAITS], one_time_keyboard=True, resize_keyboard=True)

def get_voice_keyboard():
    return ReplyKeyboardMarkup([[name] for name in VOICES.keys()], one_time_keyboard=True, resize_keyboard=True)

# ======== НАСТРОЙКИ БОТА (Голоса, языки) ========
VOICES = {
    "🧔 Мужской": "ru-RU-DmitryNeural",
    "👩 Женский": "ru-RU-SvetlanaNeural",
}
LANGUAGES = {"🇷🇺 Русский": "ru"}
CHARACTER_TRAITS = ["Смелый", "Добрый", "Любопытный", "Весёлый", "Умный"]
APPEARANCES = ["Волшебник"]

async def edge_tts_speak(text, voice="ru-RU-SvetlanaNeural"):
    try:
        communicate = edge_tts.Communicate(text, voice, rate="+5%")
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data
    except Exception as e:
        print(f"Edge TTS ошибка: {e}")
        return None

# ======== ОБРАБОТЧИКИ КОМАНД ========
async def start(update, context):
    await update.message.reply_text("✨ Привет! Я бот для аудиосказок!", reply_markup=get_main_keyboard())
async def help_command(update, context):
    await update.message.reply_text("Нажми /start и выбери «Создать сказку».", reply_markup=get_main_keyboard())
async def donate(update, context):
    await update.message.reply_text(f"❤️ Спасибо! Карта: {CARD_NUMBER}\nСсылка: {DONATE_LINK}", parse_mode="Markdown", reply_markup=get_main_keyboard())
async def my_stories(update, context):
    user_id = update.effective_user.id
    stories = get_user_stories(user_id)
    if not stories:
        await update.message.reply_text("📭 У вас пока нет сказок.", reply_markup=get_main_keyboard())
        return
    for story in stories[:5]:
        keyboard = [[InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{story['id']}")]]
        await update.message.reply_text(f"📖 {story['name']} – {story['topic']}", reply_markup=InlineKeyboardMarkup(keyboard))

# ======== ОБРАБОТКА ОПЛАТЫ (Ожидание подтверждения) ========
async def handle_payment_message(update, context):
    user_id = update.effective_user.id
    if "оплатил" in update.message.text.lower():
        db = load_db()
        if str(user_id) in db["pending_payments"]:
            plan = db["pending_payments"][str(user_id)]
            if plan == "month":
                db["payment_requests"][str(user_id)] = {"plan": "month", "status": "pending"}
                save_db(db)
                await update.message.reply_text("📩 Заявка отправлена! Ожидайте подтверждения оплаты от администратора.", reply_markup=get_main_keyboard())
                # ОПОВЕЩЕНИЕ ДЛЯ ТЕБЯ (АДМИНА)
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"💳 НОВАЯ ЗАЯВКА НА ОПЛАТУ!\n\n"
                         f"👤 Пользователь: {user_id}\n"
                         f"📅 Тариф: Месяц (299 руб.)\n"
                         f"Статус: Ожидает подтверждения\n\n"
                         f"👆 Нажмите кнопку ниже для подтверждения",
                    reply_markup=get_admin_keyboard(user_id)
                )
            elif plan == "year":
                db["payment_requests"][str(user_id)] = {"plan": "year", "status": "pending"}
                save_db(db)
                await update.message.reply_text("📩 Заявка отправлена! Ожидайте подтверждения оплаты от администратора.", reply_markup=get_main_keyboard())
                # ОПОВЕЩЕНИЕ ДЛЯ ТЕБЯ (АДМИНА)
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"💳 НОВАЯ ЗАЯВКА НА ОПЛАТУ!\n\n"
                         f"👤 Пользователь: {user_id}\n"
                         f"📅 Тариф: Год (1990 руб.)\n"
                         f"Статус: Ожидает подтверждения\n\n"
                         f"👆 Нажмите кнопку ниже для подтверждения",
                    reply_markup=get_admin_keyboard(user_id)
                )
        else:
            await update.message.reply_text("⚠️ Вы ещё не выбрали тариф. Нажмите «Создать сказку», чтобы увидеть тарифы.", reply_markup=get_main_keyboard())
    return -1

# ======== КОМАНДА ПОДТВЕРЖДЕНИЯ ОПЛАТЫ (ТОЛЬКО ДЛЯ ТЕБЯ) ========
async def confirm_payment(update, context):
    user_id = update.effective_user.id
    if str(user_id) != ADMIN_ID:
        await update.message.reply_text("⛔ Только для администратора.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Использование: /confirm 123456789")
        return

    target_user_id = str(context.args[0])
    db = load_db()

    if target_user_id in db["payment_requests"]:
        plan = db["payment_requests"][target_user_id]["plan"]
        if plan == "month":
            activate_subscription(int(target_user_id), 30)
            await update.message.reply_text(f"✅ Подписка на 1 месяц активирована для пользователя {target_user_id}!")
        elif plan == "year":
            activate_subscription(int(target_user_id), 365)
            await update.message.reply_text(f"✅ Подписка на 1 год активирована для пользователя {target_user_id}!")
        del db["payment_requests"][target_user_id]
        del db["pending_payments"][target_user_id]
        save_db(db)
    else:
        await update.message.reply_text("⚠️ Заявка от этого пользователя не найдена.")

# ======== ОБРАБОТЧИК КНОПОК ========
async def handle_buttons(update, context):
    text = update.message.text
    if text == "📖 Создать сказку":
        await story_start(update, context)
    elif text == "🎲 Удиви меня":
        await random_story(update, context)
    elif text == "📚 Мои сказки":
        await my_stories(update, context)
    elif text == "❤️ Поддержать автора":
        await donate(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    else:
        await update.message.reply_text("Напиши /start.", reply_markup=get_main_keyboard())
async def handle_payment_message(update, context):
    user_id = update.effective_user.id
    if "оплатил" in update.message.text.lower():
        db = load_db()
        if str(user_id) in db["pending_payments"]:
            plan = db["pending_payments"][str(user_id)]
            if plan == "month":
                db["payment_requests"][str(user_id)] = {"plan": "month", "status": "pending"}
                save_db(db)
                await update.message.reply_text("📩 Заявка отправлена! Ожидайте подтверждения оплаты от администратора.", reply_markup=get_main_keyboard())
                # ОПОВЕЩЕНИЕ ДЛЯ ТЕБЯ (АДМИНА)
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"💳 НОВАЯ ЗАЯВКА НА ОПЛАТУ!\n\n"
                         f"👤 Пользователь: {user_id}\n"
                         f"📅 Тариф: Месяц (299 руб.)\n"
                         f"Статус: Ожидает подтверждения\n\n"
                         f"👆 Нажмите кнопку ниже для подтверждения",
                    reply_markup=get_admin_keyboard(user_id)
                )
            elif plan == "year":
                db["payment_requests"][str(user_id)] = {"plan": "year", "status": "pending"}
                save_db(db)
                await update.message.reply_text("📩 Заявка отправлена! Ожидайте подтверждения оплаты от администратора.", reply_markup=get_main_keyboard())
                # ОПОВЕЩЕНИЕ ДЛЯ ТЕБЯ (АДМИНА)
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"💳 НОВАЯ ЗАЯВКА НА ОПЛАТУ!\n\n"
                         f"👤 Пользователь: {user_id}\n"
                         f"📅 Тариф: Год (1990 руб.)\n"
                         f"Статус: Ожидает подтверждения\n\n"
                         f"👆 Нажмите кнопку ниже для подтверждения",
                    reply_markup=get_admin_keyboard(user_id)
                )
        else:
            await update.message.reply_text("⚠️ Вы ещё не выбрали тариф. Нажмите «Создать сказку», чтобы увидеть тарифы.", reply_markup=get_main_keyboard())
    return -1
# ======== ДИАЛОГ ========
NAME, TOPIC, MORAL, LANGUAGE, TRAIT, VOICE = range(6)

async def story_start(update, context):
    user_id = update.effective_user.id
    if not can_create_story(user_id):
        db = load_db()
        if str(user_id) not in db["pending_payments"]:
            db["pending_payments"][str(user_id)] = None
            save_db(db)
        await update.message.reply_text(
            f"⚠️ Вы использовали все 3 бесплатные сказки.\n\n"
            f"💳 Чтобы продолжить, оплатите подписку:\n"
            f"Цена: {MONTHLY_PRICE} / месяц\n"
            f"Цена: {YEARLY_PRICE} / год\n"
            f"Карта: `{CARD_NUMBER}`\n\n"
            f"Выберите тариф ниже и напишите «Оплатил»!",
            parse_mode="Markdown",
            reply_markup=get_payment_keyboard()
        )
        return -1
    context.user_data['conversation'] = True
    await update.message.reply_text("📖 Напиши имя ребёнка:")
    return NAME

async def random_story(update, context):
    user_id = update.effective_user.id
    if not can_create_story(user_id):
        db = load_db()
        if str(user_id) not in db["pending_payments"]:
            db["pending_payments"][str(user_id)] = None
            save_db(db)
        await update.message.reply_text(
            f"⚠️ Вы использовали все 3 бесплатные сказки.\n\n"
            f"💳 Чтобы продолжить, оплатите подписку:\n"
            f"Цена: {MONTHLY_PRICE} / месяц\n"
            f"Цена: {YEARLY_PRICE} / год\n"
            f"Карта: `{CARD_NUMBER}`\n\n"
            f"Выберите тариф ниже и напишите «Оплатил»!",
            parse_mode="Markdown",
            reply_markup=get_payment_keyboard()
        )
        return -1
    context.user_data['conversation'] = True
    name = random.choice(["Аня", "Максим", "Соня", "Тимур"])
    topic = random.choice(["Космос", "Динозавры", "Принцессы", "Пираты", "Феи", "Лесные зверята", "Новый год", "Рыцари", "Подводный мир"])
    moral = random.choice(["дружба", "смелость", "доброта", "честность", "семья", "любознательность", "терпение"])
    language = "ru"
    trait = random.choice(CHARACTER_TRAITS)
    voice = random.choice(["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"])
    context.user_data['name'] = name
    context.user_data['topic'] = topic
    context.user_data['moral'] = moral
    context.user_data['language'] = language
    context.user_data['trait'] = trait
    context.user_data['voice'] = voice
    prompt = f"Напиши сказку для ребёнка 5-7 лет. Герой – {name}, {trait}. Тема: {topic}. Мораль: {moral}. Напиши текст БЕЗ использования звёздочек, решёток и каких-либо символов форматирования. Просто чистый текст. Обязательно закончи сказку красивым финалом!"
    await update.message.reply_text("⏳ Генерирую сказку...")
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.7
        )
        story_text = response.choices[0].message.content.strip()
        story_text = re.sub(r'\*\*', '', story_text)
        story_text = re.sub(r'\*', '', story_text)
        story_text = re.sub(r'#', '', story_text)
        story_text = re.sub(r'---', '', story_text)
        await update.message.reply_text(f"📖 {story_text}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка генерации: {e}")
        context.user_data['conversation'] = False
        return -1
    await update.message.reply_text("🔊 Озвучиваю...")
    audio_bytes = await edge_tts_speak(story_text, voice=voice)
    if audio_bytes:
        await update.message.reply_audio(audio_bytes, caption="✅ Готово!")
        save_story(update.effective_user.id, name, topic, "короткая", moral, language, trait, "Волшебник", story_text)
        increment_daily_count(update.effective_user.id)
    else:
        await update.message.reply_text("❌ Ошибка озвучки.")
    await update.message.reply_text("Что хочешь сделать дальше?", reply_markup=get_main_keyboard())
    context.user_data['conversation'] = False
    return -1

async def story_name(update, context):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("✏️ Выбери тему сказки:", reply_markup=get_topic_keyboard())
    return TOPIC

async def story_topic(update, context):
    chosen = update.message.text
    topic = chosen.replace("🚀 ", "").replace("🦕 ", "").replace("👸 ", "").replace("🏴‍☠️ ", "").replace("🧚 ", "").replace("🐾 ", "").replace("🎄 ", "").replace("🏰 ", "").replace("🌊 ", "")
    context.user_data['topic'] = topic
    await update.message.reply_text("💡 Выбери мораль сказки:", reply_markup=get_moral_keyboard())
    return MORAL

async def story_moral(update, context):
    chosen = update.message.text
    moral = chosen.replace("💛 ", "").replace("🏆 ", "").replace("🤝 ", "").replace("🔍 ", "").replace("🏡 ", "").replace("🔬 ", "").replace("🎭 ", "")
    context.user_data['moral'] = moral
    await update.message.reply_text("🌐 Выбери язык:", reply_markup=get_language_keyboard())
    return LANGUAGE

async def story_language(update, context):
    chosen = update.message.text
    language_code = None
    if chosen in LANGUAGES:
        language_code = LANGUAGES[chosen]
    else:
        for name, code in LANGUAGES.items():
            if name.lower() in chosen.lower():
                language_code = code
                break
    if language_code is None:
        await update.message.reply_text("❌ Я не понял язык. Нажми кнопку или напиши 'Русский'.", reply_markup=get_language_keyboard())
        return LANGUAGE
    context.user_data['language'] = language_code
    await update.message.reply_text("🎭 Выбери характер героя:", reply_markup=get_trait_keyboard())
    return TRAIT

async def story_trait(update, context):
    chosen = update.message.text
    trait = None
    if chosen in CHARACTER_TRAITS:
        trait = chosen
    else:
        for item in CHARACTER_TRAITS:
            if item.lower() in chosen.lower():
                trait = item
                break
    if trait is None:
        await update.message.reply_text("❌ Я не понял характер. Нажми кнопку или напиши 'Смелый'.", reply_markup=get_trait_keyboard())
        return TRAIT
    context.user_data['trait'] = trait
    await update.message.reply_text("🎤 Выбери голос:", reply_markup=get_voice_keyboard())
    return VOICE

async def story_voice(update, context):
    chosen = update.message.text
    voice_name = None
    if chosen in VOICES:
        voice_name = VOICES[chosen]
    else:
        for name, code in VOICES.items():
            if name.lower() in chosen.lower():
                voice_name = code
                break
    if voice_name is None:
        await update.message.reply_text("❌ Я не понял голос. Нажми кнопку или напиши 'Мужской'.", reply_markup=get_voice_keyboard())
        return VOICE
    context.user_data['voice'] = voice_name
    name = context.user_data['name']
    topic = context.user_data['topic']
    moral = context.user_data['moral']
    language = context.user_data['language']
    trait = context.user_data['trait']
    prompt = f"Напиши сказку для ребёнка 5-7 лет. Герой – {name}, {trait}. Тема: {topic}. Мораль: {moral}. Напиши текст БЕЗ использования звёздочек, решёток и каких-либо символов форматирования. Просто чистый текст. Обязательно закончи сказку красивым финалом!"
    await update.message.reply_text("⏳ Генерирую сказку...")
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.7
        )
        story_text = response.choices[0].message.content.strip()
        story_text = re.sub(r'\*\*', '', story_text)
        story_text = re.sub(r'\*', '', story_text)
        story_text = re.sub(r'#', '', story_text)
        story_text = re.sub(r'---', '', story_text)
        await update.message.reply_text(f"📖 {story_text}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка генерации: {e}")
        context.user_data['conversation'] = False
        return -1
    await update.message.reply_text("🔊 Озвучиваю...")
    audio_bytes = await edge_tts_speak(story_text, voice=voice_name)
    if audio_bytes:
        await update.message.reply_audio(audio_bytes, caption="✅ Готово!")
        save_story(update.effective_user.id, name, topic, "короткая", moral, language, trait, "Волшебник", story_text)
        increment_daily_count(update.effective_user.id)
    else:
        await update.message.reply_text("❌ Ошибка озвучки.")
    await update.message.reply_text("Что хочешь сделать дальше?", reply_markup=get_main_keyboard())
    context.user_data['conversation'] = False
    return -1

async def cancel(update, context):
    context.user_data['conversation'] = False
    await update.message.reply_text("Отменено.", reply_markup=get_main_keyboard())
    return -1

async def handle_inline(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "new_story":
        await query.message.reply_text("Начинаем новую сказку!")
        await story_start(query, context)
    elif data == "main_menu":
        await query.message.reply_text("Главное меню.", reply_markup=get_main_keyboard())
    elif data.startswith("delete_"):
        story_id = int(data.split("_")[1])
        delete_story(story_id, update.effective_user.id)
        await query.message.reply_text("🗑️ Сказка удалена.")
    elif data == "pay_month":
        db = load_db()
        db["pending_payments"][str(update.effective_user.id)] = "month"
        save_db(db)
        await query.message.reply_text("💳 Вы выбрали подписку на 1 месяц (299 руб.)\n\nПожалуйста, переведите 299 рублей на карту:\n`2202208186522703`\n\nПосле оплаты напишите «Оплатил»!", parse_mode="Markdown", reply_markup=get_main_keyboard())
    elif data == "pay_year":
        db = load_db()
        db["pending_payments"][str(update.effective_user.id)] = "year"
        save_db(db)
        await query.message.reply_text("💳 Вы выбрали подписку на 1 год (1990 руб.)\n\nПожалуйста, переведите 1990 рублей на карту:\n`2202208186522703`\n\nПосле оплаты напишите «Оплатил»!", parse_mode="Markdown", reply_markup=get_main_keyboard())

# ======== ИНИЦИАЛИЗАЦИЯ БОТА ========
app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("donate", donate))
app.add_handler(CommandHandler("my_stories", my_stories))
app.add_handler(CommandHandler("confirm", confirm_payment))
app.add_handler(MessageHandler(filters.Regex("оплатил") & ~filters.COMMAND, handle_payment_message))

conv = ConversationHandler(
    entry_points=[CommandHandler("story", story_start), MessageHandler(filters.Regex("📖 Создать сказку"), story_start)],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_name)],
        TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_topic)],
        MORAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_moral)],
        LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_language)],
        TRAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_trait)],
        VOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_voice)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)
app.add_handler(conv)
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
app.add_handler(CallbackQueryHandler(handle_inline))

# ======== ГОТОВО! ========
app.run_polling(allowed_updates=Update.ALL_TYPES)
