async def random_story(update, context):
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
    name = random.choice(["Аня", "Максим", "Соня", "Тимур"])
    topic = random.choice(["Космос", "Динозавры", "Принцессы", "Пираты", "Феи", "Лесные зверята", "Новый год", "Рыцари", "Подводный мир"])
    length = random.choice(["короткая", "средняя", "длинная"])
    moral = random.choice(["дружба", "смелость", "доброта", "честность", "семья", "любознательность", "терпение"])
    language = "ru"
    trait = random.choice(CHARACTER_TRAITS)
    voice = random.choice(["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"])
    context.user_data['name'] = name
    context.user_data['topic'] = topic
    context.user_data['length'] = length
    context.user_data['moral'] = moral
    context.user_data['language'] = language
    context.user_data['trait'] = trait
    context.user_data['voice'] = voice
    prompt = f"Напиши {length} сказку для ребёнка 5-7 лет. Герой – {name}, {trait}. Тема: {topic}. Мораль: {moral}. Напиши текст БЕЗ использования звёздочек, решёток и каких-либо символов форматирования. Просто чистый текст. Обязательно закончи сказку красивым финалом!"
    await update.message.reply_text("⏳ Генерирую сказку...")
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
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
        save_story(update.effective_user.id, name, topic, length, moral, language, trait, "Волшебник", story_text, audio_data=audio_bytes)
        increment_daily_count(update.effective_user.id)
    else:
        await update.message.reply_text("❌ Ошибка озвучки.")
    
    # Показываем главное меню автоматически
    await update.message.reply_text("Что хочешь сделать дальше?", reply_markup=get_main_keyboard())
    context.user_data['conversation'] = False
    return -1
