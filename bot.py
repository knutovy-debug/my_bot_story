import os
import sqlite3
import asyncio
import requests
from datetime import datetime, date
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes, CallbackQueryHandler
import openai
import edge_tts

# ===== ТОКЕНЫ (ПРОВЕРЬ ЭТИ СТРОКИ) =====
TELEGRAM_BOT_TOKEN = "8434163956:AAGlP2uk4zpAmLFGpTh8XtL5AWNJyiemgEE"
OPENAI_API_KEY = "sk-132ee0cd4cf14c10b389b7680cfcfe37"
ADMIN_ID = "8434163956"

openai.api_key = OPENAI_API_KEY

PAYMENT_LINK = "2202208186522703"

VOICES = {
    "Женский (Светлана)": "ru-RU-SvetlanaNeural",
    "Мужской (Дмитрий)": "ru-RU-DmitryNeural",
}

LANGUAGES = {
    "🇷🇺 Русский": "ru",
    "🇬🇧 Английский": "en",
}

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

# ===== БАЗА ДАННЫХ =====
def init_db():
    conn = sqlite3.connect('stories.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            topic TEXT,
            length TEXT,
            moral TEXT,
            language TEXT,
            trait TEXT,
            appearance TEXT,
            story_text TEXT,
            created_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            daily_count INTEGER DEFAULT 0,
            last_reset TEXT,
            premium INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()
init_db()

def save_story(user_id, name, topic, length, moral, language, trait, appearance, story_text):
    conn = sqlite3.connect('stories.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO stories (user_id, name, topic, length, moral, language, trait, appearance, story_text, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, name, topic, length, moral, language, trait, appearance, story_text, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user_stories(user_id):
    conn = sqlite3.connect('stories.db')
    c = conn.cursor()
    c.execute('SELECT id, name, topic, created_at FROM stories WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def delete_story(story_id, user_id):
    conn = sqlite3.connect('stories.db')
    c = conn.cursor()
    c.execute('DELETE FROM stories WHERE id = ? AND user_id = ?', (story_id, user_id))
    conn.commit()
    conn.close()

def get_user_daily_count(user_id):
    conn = sqlite3.connect('stories.db')
    c = conn.cursor()
    c.execute('SELECT daily_count, last_reset, premium FROM user_stats WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    today = date.today().isoformat()
    if row is None:
        c.execute('INSERT INTO user_stats (user_id, daily_count, last_reset, premium) VALUES (?, 0, ?, 0)', (user_id, today))
        conn.commit()
        conn.close()
        return 0
    if row[1] != today:
        c.execute('UPDATE user_stats SET daily_count = 0, last_reset = ? WHERE user_id = ?', (today, user_id))
        conn.commit()
        conn.close()
        return 0
    conn.close()
    return row[0]

def increment_daily_count(user_id):
    conn = sqlite3.connect('stories.db')
    c = conn.cursor()
    c.execute('UPDATE user_stats SET daily_count = daily_count + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def is_premium(user_id):
    conn = sqlite3.connect('stories.db')
    c = conn.cursor()
    c.execute('SELECT premium FROM user_stats WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row and row[0] == 1

def set_premium(user_id, value=1):
    conn = sqlite3.connect('stories.db')
    c = conn.cursor()
    c.execute('UPDATE user_stats SET premium = ? WHERE user_id = ?', (value, user_id))
    conn.commit()
    conn.close()

def can_create_story(user_id):
    if is_premium(user_id):
        return True
    return get_user_daily_count(user_id) < 3

# ===== КЛАВИАТУРА =====
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📖 Создать сказку")],
        [KeyboardButton("📚 Мои сказки")],
        [KeyboardButton("💳 Оплатить доступ")],
        [KeyboardButton("❤️ Поддержать автора")],
        [KeyboardButton("❓ Помощь")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update, context):
    await update.message.reply_text("✨ Привет! Я бот для аудиосказок с картинками!", reply_markup=get_main_keyboard())

async def help_command(update, context):
    await update.message.reply_text("📖 Создать сказку\n📚 Мои сказки\n💳 Оплатить доступ – снять лимит 3 сказки/день\n❤️ Поддержать автора\n❓ Помощь", reply_markup=get_main_keyboard())

async def donate(update, context):
    await update.message.reply_text(f"❤️ Спасибо за поддержку!\n\n💳 Карта: 1234 5678 9012 3456\n🔗 {PAYMENT_LINK}", reply_markup=get_main_keyboard())

async def payment(update, context):
    user_id = update.effective_user.id
    if is_premium(user_id):
        await update.message.reply_text("✅ У вас уже есть безлимитный доступ!", reply_markup=get_main_keyboard())
        return
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить", url=PAYMENT_LINK)],
        [InlineKeyboardButton("✅ Я оплатил", callback_data=f"paid_{user_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_payment")],
    ]
    await update.message.reply_text(
        "💳 Чтобы снять лимит (3 сказки/день), оплатите доступ:\n\n"
        f"🔗 {PAYMENT_LINK}\n\n"
        "После оплаты нажмите «Я оплатил».\n"
        "Администратор подтвердит доступ.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def my_stories(update, context):
    user_id = update.effective_user.id
    stories = get_user_stories(user_id)
    if not stories:
        await update.message.reply_text("📭 У вас пока нет сказок.", reply_markup=get_main_keyboard())
        return
    for story in stories[:5]:
        keyboard = [[InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{story[0]}")]]
        await update.message.reply_text(f"📖 {story[1]} – {story[2]} ({story[3][:10]})", reply_markup=InlineKeyboardMarkup(keyboard))
    if len(stories) > 5:
        await update.message.reply_text("Показаны последние 5 сказок.")

# ===== ОБРАБОТЧИК КНОПОК =====
async def handle_buttons(update, context):
    text = update.message.text
    if text == "📖 Создать сказку":
        await story_start(update, context)
    elif text == "📚 Мои сказки":
        await my_stories(update, context)
    elif text == "💳 Оплатить доступ":
        await payment(update, context)
    elif text == "❤️ Поддержать автора":
        await donate(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    else:
        await update.message.reply_text("Используйте кнопки.", reply_markup=get_main_keyboard())

# ===== ДИАЛОГ =====
NAME, TOPIC, LENGTH, MORAL, LANGUAGE, TRAIT, APPEARANCE, VOICE = range(8)

async def story_start(update, context):
    user_id = update.effective_user.id
    if not can_create_story(user_id):
        await update.message.reply_text(f"⚠️ Лимит 3 сказки/день исчерпан.\n\n💳 Нажмите «Оплатить доступ» для снятия лимита.", reply_markup=get_main_keyboard())
        return -1
    context.user_data['conversation'] = True
    await update.message.reply_text("📖 Напиши имя ребёнка:")
    return NAME

async def story_name(update, context):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("✏️ Тему (Космос, Динозавры...):")
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
    keyboard = [[name] for name in LANGUAGES.keys()]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("🌐 Язык:", reply_markup=reply_markup)
    return LANGUAGE

async def story_language(update, context):
    chosen = update.message.text
    if chosen not in LANGUAGES:
        await update.message.reply_text("❌ Выбери из списка.")
        return LANGUAGE
    context.user_data['language'] = LANGUAGES[chosen]
    keyboard = [[trait] for trait in CHARACTER_TRAITS]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("🎭 Характер героя:", reply_markup=reply_markup)
    return TRAIT

async def story_trait(update, context):
    chosen = update.message.text
    if chosen not in CHARACTER_TRAITS:
        await update.message.reply_text("❌ Выбери из списка.")
        return TRAIT
    context.user_data['trait'] = chosen
    keyboard = [[app] for app in APPEARANCES]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("🧙‍♂️ Внешность героя:", reply_markup=reply_markup)
    return APPEARANCE

async def story_appearance(update, context):
    chosen = update.message.text
    if chosen not in APPEARANCES:
        await update.message.reply_text("❌ Выбери из списка.")
        return APPEARANCE
    context.user_data['appearance'] = chosen
    keyboard = [[name] for name in VOICES.keys()]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("🎤 Голос:", reply_markup=reply_markup)
    return VOICE

async def story_voice(update, context):
    chosen = update.message.text
    if chosen not in VOICES:
        await update.message.reply_text("❌ Выбери из списка.")
        return VOICE
    voice_name = VOICES[chosen]
    context.user_data['voice'] = voice_name

    name = context.user_data['name']
    topic = context.user_data['topic']
    length = context.user_data['length']
    moral = context.user_data['moral']
    language = context.user_data['language']
    trait = context.user_data['trait']
    appearance = context.user_data['appearance']

    prompt = {
        'ru': f"Напиши {length} сказку для ребёнка 5-7 лет на русском. Герой – {name}, {trait}, {appearance}. Тема: {topic}. Мораль: {moral}.",
        'en': f"Write a {length} fairy tale for a 5-7 year old in English. Hero – {name}, {trait}, {appearance}. Theme: {topic}. Moral: {moral}.",
    }.get(language, "ru")

    await update.message.reply_text("⏳ Генерирую сказку...")
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.7,
        )
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
    try:
        url = f"https://image.pollinations.ai/prompt/{image_prompt}?width=512&height=512&nologo=true"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            await update.message.reply_photo(response.content, caption="🖼️ Иллюстрация к сказке")
        else:
            await update.message.reply_text("❌ Не удалось сгенерировать картинку.")
    except:
        await update.message.reply_text("❌ Ошибка генерации картинки.")

    keyboard = [
        [InlineKeyboardButton("📖 Создать ещё сказку", callback_data="new_story")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")],
    ]
    await update.message.reply_text("Что дальше?", reply_markup=InlineKeyboardMarkup(keyboard))

    context.user_data['conversation'] = False
    return -1

async def cancel(update, context):
    context.user_data['conversation'] = False
    await update.message.reply_text("Отменено.", reply_markup=get_main_keyboard())
    return -1

# ===== ОБРАБОТЧИК ИНЛАЙН-КНОПОК (С УВЕДОМЛЕНИЕМ АДМИНУ) =====
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

    elif data.startswith("paid_"):
        user_id = int(data.split("_")[1])
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{user_id}")],
            [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}")],
        ]
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"💳 Пользователь @{update.effective_user.username} (ID: {user_id}) оплатил доступ. Подтвердить?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await query.message.reply_text("✅ Запрос отправлен администратору. Ожидайте подтверждения.", reply_markup=get_main_keyboard())

    elif data.startswith("confirm_"):
        user_id = int(data.split("_")[1])
        set_premium(user_id, 1)
        await query.message.reply_text(f"✅ Доступ подтверждён для пользователя {user_id}!")
        try:
            await context.bot.send_message(user_id, "🎉 Ваш безлимитный доступ активирован!")
        except:
            pass

    elif data.startswith("reject_"):
        user_id = int(data.split("_")[1])
        await query.message.reply_text(f"❌ Доступ отклонён для пользователя {user_id}.")
        try:
            await context.bot.send_message(user_id, "❌ Ваш запрос отклонён.")
        except:
            pass

    elif data == "cancel_payment":
        await query.message.reply_text("Оплата отменена.", reply_markup=get_main_keyboard())

# ===== ГЛАВНАЯ =====
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

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
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("my_stories", my_stories))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(CallbackQueryHandler(handle_inline))

    print("🤖 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
