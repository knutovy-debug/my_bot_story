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
TELEGRAM_BOT_TOKEN = "8434163956:AAE_V2vlsu8Pvt1u2gz1BSfSeVXsPViQxgE"
OPENAI_API_KEY = "sk-10ce096c5fa748808b375c729610e6f3"

# ======== ОПЛАТА И РЕКВИЗИТЫ ========
CARD_NUMBER = "2202208186522703"
DONATE_LINK = "2202208186522703"
ADMIN_ID = "1177629279"  # ⚠️ ЗАМЕНИТЕ НА ВАШ ID! Узнать можно у @userinfobot

# ======== ИНИЦИАЛИЗАЦИЯ DEEPSEEK ========
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://api.deepseek.com"
)

# ======== БАЗА ДАННЫХ (JSON) ========
DB_FILE = "stories.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"stories": [], "premium_users": {}, "user_stats": {}, "payment_data": {}}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"stories": [], "premium_users": {}, "user_stats": {}, "payment_data": {}}

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

def save_story(user_id, name, topic, moral, language, trait, story_text):
    db = load_db()
    db["stories"].append({
        "id": len(db["stories"]) + 1,
        "user_id": user_id,
        "name": name,
        "topic": topic,
        "moral": moral,
        "language": language,
        "trait": trait,
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

# ======== КЛАВИАТУРА ========
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
        [InlineKeyboardButton("💳 Оплатить месяц (299 руб.)", callback_data="month_299")],
        [InlineKeyboardButton("💳 Оплатить год (1990 руб.)", callback_data="year_1990")],
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

async def edge_tts_speak(text, voice="ru-RU-SvetlanaNeural"):
    try:
        communicate = edge_tts.Communicate(text, voice, rate="-15%")
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data
    except Exception as e:
        print(f"Edge TTS ошибка: {e}")
        return None
async def share_bot(update, context):
    await update.message.reply_text(
        "🎁 Поделись ботом с друзьями! Отправь им ссылку:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Отправить друзьям", switch_inline_query="")]
        ])
    )
# ======== ОБРАБОТЧИКИ КОМАНД ========
async def start(update, context):
    await update.message.reply_text("✨ Привет! Я бот для аудиосказок!", reply_markup=get_main_keyboard())

async def help_command(update, context):
    await update.message.reply_text("Нажми /start и выбери «Создать сказку».", reply_markup=get_main_keyboard())

async def donate(update, context):
    await update.message.reply_text(
        f"❤️ Спасибо за поддержку!\n"
        f"💳 Карта: `{CARD_NUMBER}`\n"
        f"Или воспользуйтесь кнопками ниже для оформления подписки:",
        parse_mode="Markdown",
        reply_markup=get_payment_keyboard()
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

# ======== ОБРАБОТКА ОПЛАТЫ (Кнопки оплаты) ========
async def payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data

    # Обработка удаления сказки
    if data.startswith("delete_"):
        story_id = int(data.split("_")[1])
        delete_story(story_id, user_id)
        await query.edit_message_text("🗑️ Сказка удалена!")
        return

    # Обработка подтверждения/отклонения администратором
    if data.startswith("confirm_") or data.startswith("reject_"):
        await confirm_handler(update, context)
        return

    # Обработка выбора тарифа
    if data == "month_299":
        price, period, days = "299 ₽", "1 месяц", 30
    elif data == "year_1990":
        price, period, days = "1990 ₽", "1 год", 365
    else:
        return

    db = load_db()
    db["payment_data"][str(user_id)] = {
        "price": price,
        "period": period,
        "days": days,
        "username": update.effective_user.username or "Нет username",
        "full_name": update.effective_user.full_name
    }
    save_db(db)

    await query.edit_message_text(
        f"💳 Вы выбрали подписку на {period} за {price}!\n\n"
        f"Для оплаты переведите {price} на карту:\n"
        f"`{CARD_NUMBER}`\n\n"
        f"После перевода напишите слово «Оплатил»",
        parse_mode="Markdown"
    )

# ======== ОБРАБОТКА "ОПЛАТИЛ" (Уведомление для админа) ========
async def payment_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if "оплатил" in text.lower():
        db = load_db()
        payment_info = db["payment_data"].get(str(user_id), {
            "price": "Неизвестно", 
            "period": "Неизвестно", 
            "days": 30,
            "username": "Нет username",
            "full_name": "Неизвестно"
        })

        # Отправляем уведомление администратору
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"💳 **НОВЫЙ ЗАПРОС НА ОПЛАТУ!**\n\n"
                 f"👤 Пользователь: {payment_info.get('full_name', 'Неизвестно')}\n"
                 f"🆔 ID: `{user_id}`\n"
                 f"📱 Username: @{payment_info.get('username', 'Нет')}\n"
                 f"💵 Тариф: {payment_info['period']} за {payment_info['price']}\n\n"
                 f"Проверьте поступление средств и подтвердите:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{user_id}")],
                [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}")]
            ])
        )
        await update.message.reply_text("✅ Спасибо! Ваш запрос отправлен администратору. Ожидайте подтверждения.")
    else:
        await update.message.reply_text("Чтобы оплатить, нажмите на кнопку тарифа и следуйте инструкции.")

# ======== ОБРАБОТКА ОТВЕТА (Подтверждение/Отклонение) ========
async def confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = update.effective_user.id

    # Проверяем, что это администратор
    if str(admin_id) != ADMIN_ID:
        await query.answer("⛔ Только для администратора!", show_alert=True)
        return

    data = query.data
    parts = data.split("_")
    
    if len(parts) < 2:
        return
    
    action = parts[0]
    target_user = parts[1]
    
    db = load_db()
    payment_info = db["payment_data"].get(target_user, {"days": 30})

    if action == "confirm":
        days = payment_info.get("days", 30)
        activate_subscription(int(target_user), days)
        await query.edit_message_text(f"✅ Подписка для пользователя {target_user} активирована на {days} дней!")
        
        # Отправляем уведомление пользователю
        try:
            await context.bot.send_message(
                chat_id=target_user, 
                text=f"🎉 Отлично! Оплата подтверждена!\n"
                     f"Теперь у вас безлимитный доступ на {payment_info.get('period', '30 дней')}!"
            )
        except Exception as e:
            print(f"Не удалось отправить уведомление пользователю: {e}")
            
    elif action == "reject":
        await query.edit_message_text(f"❌ Оплата от пользователя {target_user} отклонена!")
        
        # Отправляем уведомление пользователю
        try:
            await context.bot.send_message(
                chat_id=target_user, 
                text="❌ К сожалению, оплата отклонена. Пожалуйста, проверьте перевод и попробуйте еще раз."
            )
        except Exception as e:
            print(f"Не удалось отправить уведомление пользователю: {e}")

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
    elif text == "📤 Поделиться с друзьями":
        await share_bot(update, context)
    else:
        await update.message.reply_text("Напиши /start.", reply_markup=get_main_keyboard())

# ======== ДИАЛОГ ========
NAME, TOPIC, MORAL, LANGUAGE, TRAIT, VOICE = range(6)

async def story_start(update, context):
    user_id = update.effective_user.id
    if not can_create_story(user_id):
        await update.message.reply_text(
            f"⚠️ Вы использовали все 3 бесплатные сказки.\n\n"
            f"💳 Чтобы продолжить, оплатите подписку:\n"
            f"• 299 руб. / месяц\n"
            f"• 1990 руб. / год\n\n"
            f"Выберите тариф ниже:",
            reply_markup=get_payment_keyboard()
        )
        return ConversationHandler.END
    
    context.user_data['conversation'] = True
    await update.message.reply_text("📖 Напиши имя ребёнка:")
    return NAME

async def random_story(update, context):
    user_id = update.effective_user.id
    if not can_create_story(user_id):
        await update.message.reply_text(
            f"⚠️ Вы использовали все 3 бесплатные сказки.\n\n"
            f"💳 Чтобы продолжить, оплатите подписку:\n"
            f"• 299 руб. / месяц\n"
            f"• 1990 руб. / год\n\n"
            f"Выберите тариф ниже:",
            reply_markup=get_payment_keyboard()
        )
        return ConversationHandler.END
    
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
            max_tokens=400,
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
        return ConversationHandler.END
    
    await update.message.reply_text("🔊 Озвучиваю...")
    audio_bytes = await edge_tts_speak(story_text, voice=voice)
    
    if audio_bytes:
        await update.message.reply_audio(audio_bytes, caption="✅ Готово!")
        save_story(update.effective_user.id, name, topic, moral, language, trait, story_text)
        increment_daily_count(update.effective_user.id)
    else:
        await update.message.reply_text("❌ Ошибка озвучки.")
    
    await update.message.reply_text("Что хочешь сделать дальше?", reply_markup=get_main_keyboard())
    context.user_data['conversation'] = False
    return ConversationHandler.END

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
    # Пропускаем выбор языка, русский ставим автоматически
    context.user_data['language'] = "ru"
    await update.message.reply_text("🎭 Выбери характер героя:", reply_markup=get_trait_keyboard())
    return TRAIT

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
            max_tokens=1000,
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
        return ConversationHandler.END
    
    await update.message.reply_text("🔊 Озвучиваю...")
    audio_bytes = await edge_tts_speak(story_text, voice=voice_name)
    
    if audio_bytes:
        await update.message.reply_audio(audio_bytes, caption="✅ Готово!")
        save_story(update.effective_user.id, name, topic, moral, language, trait, story_text)
        increment_daily_count(update.effective_user.id)
    else:
        await update.message.reply_text("❌ Ошибка озвучки.")
    
    await update.message.reply_text("Что хочешь сделать дальше?", reply_markup=get_main_keyboard())
    context.user_data['conversation'] = False
    return ConversationHandler.END

async def cancel(update, context):
    context.user_data['conversation'] = False
    await update.message.reply_text("Отменено.", reply_markup=get_main_keyboard())
    return ConversationHandler.END

# ======== ИНИЦИАЛИЗАЦИЯ БОТА ========
app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("donate", donate))
app.add_handler(CommandHandler("my_stories", my_stories))

# Регистрируем обработчик "оплатил"
app.add_handler(MessageHandler(filters.Regex(r"(?i)оплатил") & ~filters.COMMAND, payment_message_handler))

# Conversation handler для создания сказки
conv = ConversationHandler(
    entry_points=[
        CommandHandler("story", story_start),
        MessageHandler(filters.Regex("📖 Создать сказку"), story_start)
    ],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_name)],
        TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_topic)],
        MORAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_moral)],
        TRAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_trait)],
        VOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, story_voice)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)
app.add_handler(conv)

# Обработчик callback'ов
app.add_handler(CallbackQueryHandler(payment_handler))

# Обработчик обычных сообщений
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

# ======== ЗАПУСК ========
if __name__ == "__main__":
    print("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
