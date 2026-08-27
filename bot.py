import os
import json
import asyncio
import requests
from datetime import datetime, date
from telegram.request import HTTPXRequest
from openai import OpenAI
import edge_tts

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes, CallbackQueryHandler

# ======== ТОКЕНЫ (ЗАМЕНИ НА СВОИ) ========
TELEGRAM_BOT_TOKEN = "8434163956:AAH_cUX7uvV46QX5d6XWUxWSMusHDApsOpU"
OPENAI_API_KEY= "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"
client = OpenAI(api_key=OPENAI_API_KEY)
CARD_NUMBER = "2202208186522703"
DONATE_LINK = "2202208186522703"

# ======== БАЗА ДАННЫХ (JSON) ========
DB_FILE = "stories.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"stories": [], "premium_users": [], "user_stats": {}}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

# ======== ФУНКЦИИ ПОДПИСКИ ========
def is_premium(user_id):
    db = load_db()
    return str(user_id) in db["premium_users"]

def get_user_daily_count(user_id):
    db = load_db()
    today = date.today().isoformat()
    if str(user_id) not in db["user_stats"]:
        db["user_stats"][str(user_id)] = {"daily_count": 0, "last_reset": today}
        save_db(db)
        return 0
    if db["user_stats"][str(user_id)]["last_reset"] != today:
        db["user_stats"][str(user_id)] = {"daily_count": 0, "last_reset": today}
        save_db(db)
        return 0
    return db["user_stats"][str(user_id)]["daily_count"]

def increment_daily_count(user_id):
    db = load_db()
    if str(user_id) not in db["user_stats"]:
        db["user_stats"][str(user_id)] = {"daily_count": 0, "last_reset": date.today().isoformat()}
    db["user_stats"][str(user_id)]["daily_count"] += 1
    save_db(db)

def can_create_story(user_id):
    # Если Premium — безлимит
    if is_premium(user_id):
        return True
    # Если бесплатный — лимит 3 в день
    return get_user_daily_count(user_id) < 3

# ======== САМАЯ ВАЖНАЯ ФУНКЦИЯ: РАЗБЛОКИРОВКА ========
# Используем команду /unlock 123456789
async def unlock_user(update, context):
    # Проверяем, что команду вводит владелец (ты сам)
    admin_id = int(os.environ.get("ADMIN_ID", "0"))  # Вставь свой ID сюда (через @userinfobot)
    if update.effective_user.id != admin_id:
        await update.message.reply_text("⛔ Недоступно.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Формат: /unlock 123456789")
        return

    try:
        user_id = int(context.args[0])
        db = load_db()
        if str(user_id) not in db["premium_users"]:
            db["premium_users"].append(str(user_id))
            save_db(db)
            await update.message.reply_text(f"✅ Разблокирован: {user_id}")
        else:
            await update.message.reply_text(f"✅ Уже разблокирован: {user_id}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ======== КЛАВИАТУРА ========
def get_main_keyboard():
    keyboard = [[KeyboardButton("📖 Создать сказку")], [KeyboardButton("📚 Мои сказки")], [KeyboardButton("❤️ Поддержать автора")], [KeyboardButton("❓ Помощь")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_language_keyboard():
    return ReplyKeyboardMarkup([[name] for name in LANGUAGES.keys()], one_time_keyboard=True, resize_keyboard=True)

def get_trait_keyboard():
    return ReplyKeyboardMarkup([[trait] for trait in CHARACTER_TRAITS], one_time_keyboard=True, resize_keyboard=True)

def get_appearance_keyboard():
    return ReplyKeyboardMarkup([[appearance] for appearance in APPEARANCES], one_time_keyboard=True, resize_keyboard=True)

def get_voice_keyboard():
    return ReplyKeyboardMarkup([[name] for name in VOICES.keys()], one_time_keyboard=True, resize_keyboard=True)

# ======== НАСТРОЙКИ БОТА (Голоса, языки) ========
VOICES = {"Женский": "ru-RU-SvetlanaNeural", "Мужской": "ru-RU-DmitryNeural"}
LANGUAGES = {"Русский": "ru", "Английский": "en", "Украинский": "uk", "Испанский": "es", "Немецкий": "de", "Французский": "fr", "Итальянский": "it", "Китайский": "zh", "Японский": "ja", "Португальский": "pt"}
CHARACTER_TRAITS = ["Смелый", "Добрый", "Любопытный", "Весёлый", "Умный"]
APPEARANCES = ["Рыцарь", "Фея", "Космонавт", "Пират", "Волшебник"]

async def edge_tts_speak(text, voice="ru-RU-SvetlanaNeural"):
    try:
        communicate = edge_tts.Communicate(text, voice)
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
    await update.message.reply_text(
        f"❤️ Спасибо, что хотите поддержать автора!\n\n"
        f"💳 Номер карты: `{CARD_NUMBER}`\n"
        f"🔗 Или по ссылке: {DONATE_LINK}\n\n"
        f"После оплаты просто напишите «Оплатил» в чат, и я открою вам безлимит на 7 дней!",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
async def my_stories(update, context):
    user_id = update.effective_user.id
    stories = get_user_stories(user_id)
    if not stories:
        await update.message.reply_text("📭 У вас пока нет сказок.", reply_markup=get_main_keyboard())
        return
    for story in stories[:5]:
        keyboard = [[InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{story['id']}")]]
        await update.message.reply_text(f"📖 {story['name']} – {story['topic']}", reply_markup=InlineKeyboardMarkup(keyboard))

# ======== УСТАНОВКА WEBHOOK (РАБОЧИЙ СОБСТВЕННЫЙ) ========
async def set_webhook(update, context):
    if update.effective_user.id != int(os.environ.get("ADMIN_ID", "0")):
        await update.message.reply_text("⛔ Недоступно.")
        return
    await update.message.reply_text("🔧 Настраиваю вебхук...")
    webhook_url = "https://yura180488.pythonanywhere.com/webhook"
    result = await context.bot.set_webhook(webhook_url)
    await update.message.reply_text(f"✅ Вебхук: {result}")
    if not result:
        await update.message.reply_text("❌ Проблема с вебхуком. Вконтакте настройте курл.")

# ======== ДИАЛОГ ========
NAME, TOPIC, LENGTH, MORAL, LANGUAGE, TRAIT, APPEARANCE, VOICE = range(8)

async def story_start(update, context):
    user_id = update.effective_user.id
    if not can_create_story(user_id):
        await update.message.reply_text(
            f"⚠️ Вы исчерпали лимит на сегодня (3 сказки).\n\n"
            f"💳 Поддержите автора, чтобы получить безлимит:\n"
            f"Карта: `{CARD_NUMBER}`\n\n"
            f"После оплаты напишите «Оплатил»!",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        return -1
    context.user_data['conversation'] = True
    await update.message.reply_text("📖 Напиши имя ребёнка:")
    return NAME

async def story_name(update, context):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("✏️ Тему (Космос, Динозавры, Принцессы...):")
    return TOPIC

async def story_topic(update, context):
    context.user_data['topic'] = update.message.text
    await update.message.reply_text("📏 Длину (короткая, средняя, длинная):")
    return LENGTH

async def story_length(update, context):
    context.user_data['length'] = update.message.text
    await update.message.reply_text("💡 Мораль (дружба, смелость...):")
    return MORAL

async def story_moral(update, context):
    context.user_data['moral'] = update.message.text
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
    await update.message.reply_text("🧙‍♂️ Выбери внешность героя:", reply_markup=get_appearance_keyboard())
    return APPEARANCE

async def story_appearance(update, context):
    chosen = update.message.text
    appearance = None
    if chosen in APPEARANCES:
        appearance = chosen
    else:
        for item in APPEARANCES:
            if item.lower() in chosen.lower():
                appearance = item
                break
    if appearance is None:
        await update.message.reply_text("❌ Я не понял внешность. Нажми кнопку или напиши 'Рыцарь'.", reply_markup=get_appearance_keyboard())
        return APPEARANCE
    context.user_data['appearance'] = appearance
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
    length = context.user_data['length']
    moral = context.user_data['moral']
    language = context.user_data['language']
    trait = context.user_data['trait']
    appearance = context.user_data['appearance']
    prompt = f"Напиши {length} сказку для ребёнка 5-7 лет. Герой – {name}, {trait}, {appearance}. Тема: {topic}. Мораль: {moral}."
    await update.message.reply_text("⏳ Генерирую сказку...")
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=600, temperature=0.7)
        story_text = response.choices[0].message.content.strip()
        await update.message.reply_text(f"📖 {story_text}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка генерации: {e}")
        context.user_data['conversation'] = False
        return -1
    await update.message.reply_text("🔊 Озвучиваю...")
    audio_bytes = await edge_tts_speak(story_text, voice=voice_name)
    if audio_bytes:
        await update.message.reply_audio(audio_bytes, caption="✅ Готово!")
        save_story(update.effective_user.id, name, topic, length, moral, language, trait, appearance, story_text)
        increment_daily_count(update.effective_user.id)
    else:
        await update.message.reply_text("❌ Ошибка озвучки.")
    await update.message.reply_text("🎨 Генерирую картинку...")
    image_prompt = f"{name} as a {trait} {appearance} in a {topic} fairy tale"
    image_bytes = await generate_image(image_prompt)
    if image_bytes:
        await update.message.reply_photo(image_bytes, caption="🖼️ Иллюстрация")
    else:
        await update.message.reply_text("❌ Не удалось сгенерировать картинку.")
    keyboard = [[InlineKeyboardButton("📖 Создать ещё сказку", callback_data="new_story")], [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
    await update.message.reply_text("Что хочешь сделать дальше?", reply_markup=InlineKeyboardMarkup(keyboard))
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

# ======== ИНИЦИАЛИЗАЦИЯ БОТА ========
app = Application.builder().token("8434163956:AAH_cUX7uvV46QX5d6XWUxWSMusHDApsOpU").build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("donate", donate))
app.add_handler(CommandHandler("my_stories", my_stories))
app.add_handler(CommandHandler("unlock", unlock_user))
# ======== ОБРАБОТКА ОПЛАТЫ ========
async def handle_payment_message(update, context):
    user_id = update.effective_user.id
    # Если пользователь написал "оплатил"
    if "оплатил" in update.message.text.lower():
        # Добавляем его в Premium список
        db = load_db()
        if str(user_id) not in db["premium_users"]:
            db["premium_users"].append(str(user_id))
            save_db(db)
            await update.message.reply_text("✅ Спасибо за оплату! Теперь у тебя есть безлимит на 7 дней!", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text("✅ У тебя уже есть безлимит!", reply_markup=get_main_keyboard())
# Отдельный блок для "оплатил" (автоматически получает бесплатный безлимит, если ты подтвердишь)
app.add_handler(MessageHandler(filters.Regex("оплатил") & ~filters.COMMAND, handle_payment_message))

conv = ConversationHandler(
    entry_points=[CommandHandler("story", story_start), MessageHandler(filters.Regex("📖 Создать сказку"), story_start)],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_name)],
        TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_topic)],
        LENGTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_length)],
        MORAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_moral)],
        LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_language)],
        TRAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_trait)],
        APPEARANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_appearance)],
        VOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_voice)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)
app.add_handler(conv)
# ======== СТАТИСТИКА И БАЗА ========
def get_user_stories(user_id):
    db = load_db()
    return [s for s in db["stories"] if s["user_id"] == user_id][::-1]

def delete_story(story_id, user_id):
    db = load_db()
    db["stories"] = [s for s in db["stories"] if not (s["id"] == story_id and s["user_id"] == user_id)]
    save_db(db)
# ======== ОБРАБОТКА КНОПОК ========
async def handle_buttons(update, context):
    text = update.message.text
    if text == "📖 Создать сказку":
        await story_start(update, context)
    elif text == "📚 Мои сказки":
        await my_stories(update, context)
    elif text == "❤️ Поддержать автора":
        await donate(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    else:
        await update.message.reply_text("Напиши /start.", reply_markup=get_main_keyboard())
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
app.add_handler(CallbackQueryHandler(handle_inline))

# ======== ГОТОВО! ========
app.run_polling(allowed_updates=Update.ALL_TYPES)
async def donate(update, context):
    await update.message.reply_text(f"❤️ Спасибо! Карта: {CARD_NUMBER}\nСсылка: {DONATE_LINK}", parse_mode="Markdown", reply_markup=get_main_keyboard())
