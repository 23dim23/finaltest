import sqlite3
import asyncio
import re
import requests
import html
import sys
from pyrogram import Client, enums

# ДОБАВЛЕНО: защита от дубликатов сообщений
sent_messages = set()

# --- НАСТРОЙКИ ---
API_ID = 33481567 
API_HASH = "93d073404049ef77e94be613d29fb57d"
BOT_TOKEN = "7941528893:AAFCMSzgUH3fuMc2cTXzKaPJKXTjZYXNkS4" 
TARGET_GROUP_ID = -1003455134116 
REPORT_TOPIC_ID = None

app = Client("my_account", api_id=API_ID, api_hash=API_HASH)

# НОВОЕ: Функция для получения списка особых чатов из БД
def get_special_chats():
    """Получение списка ID чатов, где нужен особый метод поиска контакта"""
    try:
        conn = sqlite3.connect("parser_data.db")
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM special_chats")
        special_chats = [int(row[0]) for row in cursor.fetchall()]
        conn.close()
        return special_chats
    except Exception as e:
        print(f"❌ Ошибка чтения особых чатов: {e}")
        return []

# НОВОЕ: Специальный метод поиска контакта для проблемных чатов (БЕЗ get_users)
async def get_contact_special_method(client, message):
    """Особый метод: берём контакт напрямую из message, без get_users"""
    try:
        print(f"   ⭐ Применяем ОСОБЫЙ метод для чата {message.chat.id}")
        
        # Пытаемся получить контакт напрямую из message.from_user
        if message.from_user:
            if message.from_user.username:
                contact = f"@{message.from_user.username}"
                author_id = message.from_user.id
                print(f"   ✅ Особый метод: найден @{message.from_user.username}")
                return contact, author_id
            elif message.from_user.id:
                # Если нет username, но есть ID - используем имя
                if message.from_user.first_name:
                    name = html.escape(message.from_user.first_name)
                    contact = name
                    author_id = message.from_user.id
                    print(f"   ✅ Особый метод: найдено имя {name} (ID: {author_id})")
                    return contact, author_id
                else:
                    contact = "Автор"
                    author_id = message.from_user.id
                    print(f"   ✅ Особый метод: найден автор с ID {author_id}")
                    return contact, author_id
        
        # Если message.from_user нет, пробуем через reply_to_message
        if message.reply_to_message and message.reply_to_message.from_user:
            reply_user = message.reply_to_message.from_user
            if reply_user.username:
                print(f"   ✅ Особый метод (reply): @{reply_user.username}")
                return f"@{reply_user.username}", reply_user.id
            elif reply_user.id:
                name = html.escape(reply_user.first_name or 'Автор')
                print(f"   ✅ Особый метод (reply): имя {name}")
                return name, reply_user.id
        
        print(f"   ❌ Особый метод: нет данных об авторе в message")
        return None, None
        
    except Exception as e:
        print(f"   ⚠️ Ошибка особого метода: {e}")
        return None, None

# НОВОЕ: Функция для получения username автора (обычный метод, БЕЗ get_users)
async def get_author_username(client, message):
    """Получает username автора сообщения без использования get_users"""
    try:
        # Прямой доступ через from_user
        if message.from_user:
            if message.from_user.username:
                print(f"   ✅ Найден username: @{message.from_user.username}")
                return f"@{message.from_user.username}", message.from_user.id
            elif message.from_user.id:
                # Если нет username, но есть ID - используем имя
                if message.from_user.first_name:
                    name = html.escape(message.from_user.first_name)
                    print(f"   ✅ Найдено имя: {name}")
                    return name, message.from_user.id
                else:
                    print(f"   ✅ Найден автор с ID {message.from_user.id}")
                    return "Автор", message.from_user.id
        
        return None, None
    except Exception as e:
        print(f"⚠️ Ошибка получения автора: {e}")
        return None, None

def get_data_from_db():
    """Получение свежих настроек из БД перед каждой проверкой"""
    try:
        conn = sqlite3.connect("parser_data.db")
        cursor = conn.cursor()
        
        cursor.execute("SELECT url FROM channels")
        channels = [str(row[0]).strip().lower() for row in cursor.fetchall()]
        
        cursor.execute("SELECT word FROM keywords")
        keywords = [str(row[0]).lower().strip() for row in cursor.fetchall() if row[0]]
        
        cursor.execute("SELECT word FROM stop_words")
        stop_words = [str(row[0]).lower().strip() for row in cursor.fetchall() if row[0]]
        
        conn.close()
        return channels, keywords, stop_words
    except Exception as e:
        print(f"❌ Ошибка чтения БД: {e}")
        return [], [], []

# УПРОЩЁННАЯ версия отправки - сразу правильные callback_data
def send_to_moderation(chat_id, thread_id, text, author_id=None, message_link=None, is_special=False, temp_message_id=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    if is_special:
        # Для особых чатов - формируем правильные кнопки СРАЗУ
        # Но мы не знаем message_id заранее, поэтому используем временный placeholder
        # и потом обновим через editMessageReplyMarkup
        keyboard = [
            [
                {"text": "⏳ Загрузка...", "callback_data": "loading"}
            ]
        ]
    else:
        # Обычная клавиатура
        keyboard = [
            [
                {"text": "✅ Опубликовать", "callback_data": "pub_approve"},
                {"text": "❌ Отклонить", "callback_data": "pub_decline"}
            ]
        ]
        if message_link:
            keyboard.append([
                {"text": "🔗 Источник", "url": message_link}
            ])
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {
            "inline_keyboard": keyboard
        }
    }
    
    if thread_id:
        payload["message_thread_id"] = thread_id
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        res = r.json()
        
        if res.get("ok") and is_special:
            # Получили ID сообщения, теперь обновляем клавиатуру
            message_id = res.get("result", {}).get("message_id")
            if message_id:
                update_url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageReplyMarkup"
                
                # Формируем правильные кнопки
                buttons = []
                if message_link:
                    buttons.append({"text": "🔗 Источник", "url": message_link})
                buttons.append({"text": "✏️ Ввести контакт", "callback_data": f"edit_contact_{message_id}"})
                buttons.append({"text": "✅ Опубликовать", "callback_data": f"pub_approve_special_{message_id}"})
                buttons.append({"text": "❌ Отклонить", "callback_data": f"pub_decline_special_{message_id}"})
                
                # Разбиваем по 2 кнопки в ряд
                keyboard_rows = []
                for i in range(0, len(buttons), 2):
                    keyboard_rows.append(buttons[i:i+2])
                
                update_payload = {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "reply_markup": {
                        "inline_keyboard": keyboard_rows
                    }
                }
                update_res = requests.post(update_url, json=update_payload, timeout=10)
                if update_res.status_code == 200:
                    print(f"✅ Кнопки для особого чата обновлены (message_id: {message_id})")
                else:
                    print(f"⚠️ Ошибка обновления кнопок: {update_res.text}")
        
        if not res.get("ok"):
            print(f"❌ Ошибка Telegram API: {res.get('description')}")
            if "thread not found" in str(res).lower() and thread_id:
                payload.pop("message_thread_id", None)
                requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Ошибка при отправке модератору: {e}")

@app.on_message()
async def check_messages(client, message):
    # ДОБАВЛЕНО: защита от дубликатов
    msg_id = f"{message.chat.id}_{message.id}"
    if msg_id in sent_messages:
        return
    sent_messages.add(msg_id)
    
    # Ограничиваем размер множества
    if len(sent_messages) > 10000:
        sent_messages.clear()
    
    # НОВОЕ: Получаем список особых чатов
    special_chats = get_special_chats()
    
    # ===== ОТЛАДКА =====
    print(f"\n{'='*50}")
    print(f"🔍 Обработка сообщения ID: {message.id}")
    print(f"   Чат ID: {message.chat.id}")
    print(f"   Тип чата: {message.chat.type}")
    print(f"   Особый чат: {'✅ ДА' if message.chat.id in special_chats else '❌ НЕТ'}")
    if message.from_user:
        print(f"   Автор username: @{message.from_user.username}" if message.from_user.username else f"   Автор ID: {message.from_user.id}, username: отсутствует")
        print(f"   Автор first_name: {message.from_user.first_name}")
    else:
        print(f"   Автор: не определён (message.from_user = None)")
    print(f"{'='*50}")
    
    # РАСШИРЕННАЯ ОТЛАДКА ДЛЯ ОСОБОГО ЧАТА
    if message.chat.id in special_chats:
        print(f"\n🔴🔴🔴 ДЕТАЛЬНАЯ ОТЛАДКА ДЛЯ ОСОБОГО ЧАТА 🔴🔴🔴")
        print(f"message.sender_chat: {message.sender_chat}")
        print(f"message.date: {message.date}")
        print(f"message.reply_to_message: {message.reply_to_message}")
        
        # Пробуем получить автора через chat_history
        try:
            async for msg in client.get_chat_history(message.chat.id, limit=10):
                if msg.id == message.id:
                    print(f"Найдено сообщение в истории:")
                    print(f"  msg.from_user: {msg.from_user}")
                    print(f"  msg.sender_chat: {msg.sender_chat}")
                    if msg.from_user:
                        print(f"  msg.from_user.username: {msg.from_user.username}")
                        print(f"  msg.from_user.first_name: {msg.from_user.first_name}")
                    break
        except Exception as e:
            print(f"Ошибка истории: {e}")
        print(f"🔴🔴🔴 КОНЕЦ ОТЛАДКИ 🔴🔴🔴\n")
    # ===================
    
    if not message.chat or message.chat.id == TARGET_GROUP_ID:
        return

    content = message.text or message.caption
    if not content:
        return

    channels_db, keywords, stop_words = get_data_from_db()
    msg_text_lower = content.lower()

    is_target = False
    cid_full = str(message.chat.id)
    cid_short = cid_full.replace("-100", "")
    uname = (message.chat.username or "").lower()
    raw_topic_id = getattr(message, "message_thread_id", None)
    current_thread_id = str(raw_topic_id) if raw_topic_id else None

    for conf in channels_db:
        clean_conf = conf.replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '').strip()
        target_chat = clean_conf
        target_topic = None

        if "/" in clean_conf:
            parts = clean_conf.rstrip('/').split('/')
            if parts[0] == "c" and len(parts) >= 3:
                target_chat, target_topic = parts[1], parts[2]
            elif len(parts) >= 2:
                target_chat, target_topic = parts[0], parts[1]

        if (target_chat == uname) or (target_chat == cid_full) or (target_chat == cid_short):
            if target_topic:
                if current_thread_id == target_topic:
                    is_target = True
                    break
            else:
                is_target = True
                break

    if not is_target:
        return

    for stop_word in stop_words:
        if stop_word and stop_word in msg_text_lower:
            print(f"🚫 Пропущено (стоп-слово): '{stop_word}'")
            return

    found_keyword = False
    for word in keywords:
        if not word: continue
        pattern = rf"(?:^|[^а-яёa-z0-9]){re.escape(word)}(?:$|[^а-яёa-z0-9])"
        try:
            if re.search(pattern, msg_text_lower):
                found_keyword = True
                break
        except:
            if word in msg_text_lower:
                found_keyword = True
                break

    if found_keyword:
        # --- 1. СОХРАНЕНИЕ ФОРМАТИРОВАНИЯ ---
        if message.text:
            body_html = message.text.html
        elif message.caption:
            body_html = html.escape(message.caption)
        else:
            return

        # --- 2. ПОИСК КОНТАКТА ---
        contact = "Не указан"
        author_id = None
        source_username = message.chat.username

        # НОВОЕ: Проверяем, является ли чат особым
        is_special = message.chat.id in special_chats
        
        if is_special:
            print(f"🔧 ЧАТ В СПИСКЕ ОСОБЫХ! Применяем специальный метод...")
            # Для особых чатов сразу используем специальный метод
            special_contact, special_author_id = await get_contact_special_method(client, message)
            if special_contact:
                contact = special_contact
                author_id = special_author_id
                print(f"📱 Особый метод сработал: {contact}")
            else:
                print(f"⚠️ Особый метод не дал результат, пробуем обычные способы...")
        
        # Если ещё не нашли контакт (обычный чат или особый не помог)
        if contact == "Не указан":
            # Сначала ищем в сущностях (скрытые ссылки и упоминания)
            entities = message.entities or message.caption_entities
            if entities:
                for entity in entities:
                    if entity.type == enums.MessageEntityType.TEXT_LINK:
                        if "t.me/" in entity.url or "tg://user" in entity.url:
                            if source_username and source_username.lower() in entity.url.lower():
                                continue
                            contact = entity.url
                            print(f"🔗 Контакт найден в TEXT_LINK: {contact}")
                            break
                    elif entity.type == enums.MessageEntityType.MENTION:
                        mention = content[entity.offset:entity.offset+entity.length]
                        if source_username and mention.lower().strip('@') == source_username.lower():
                            continue
                        contact = mention
                        print(f"📢 Контакт найден в MENTION: {contact}")
                        break

            # Если в сущностях не нашли, ищем регуляркой в тексте
            if contact == "Не указан":
                found_usernames = re.findall(r"@[a-zA-Z0-9_]{5,}", content)
                for fu in found_usernames:
                    if source_username and fu.lower().strip('@') == source_username.lower():
                        continue
                    contact = fu
                    print(f"📝 Контакт найден регуляркой: {contact}")
                    break

        # Если всё ещё не нашли - пробуем через профиль автора (только для обычных чатов)
        if contact == "Не указан" and not is_special:
            print(f"🔍 Контакт не найден в тексте, ищем через профиль автора...")
            author_contact, author_id = await get_author_username(client, message)
            
            if author_contact:
                contact = author_contact
                print(f"📱 Контакт получен через профиль автора: {contact} (ID: {author_id})")
            else:
                # Запасной вариант - поиск email или телефона
                email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                phone_pattern = r'\+?[\d\s\-\(\)]{10,}'
                
                email_match = re.search(email_pattern, content)
                phone_match = re.search(phone_pattern, content)
                
                if email_match:
                    contact = email_match.group()
                    print(f"📧 Контакт найден как email: {contact}")
                elif phone_match:
                    contact = phone_match.group()
                    print(f"📞 Контакт найден как телефон: {contact}")
                else:
                    contact = "<i>⚠️ Контакт не найден (укажите @username или добавьте контакт в текст)</i>"
                    print(f"⚠️ Контакт не найден в сообщении из чата {message.chat.id}")

        # --- 3. ФОРМИРОВАНИЕ ПОСТА ---
        header = "<b>| 🇻 🇦 🇨 🇦 🇳 🇨 🇾 |</b>\n\n"
        contact_block = f"<b>Контакт для связи:</b>\n{contact}\n\n"
        instruction = (
            "<b><code>Для публикации вакансии\\резюме, напишите заявку в </code>"
            "<a href='https://t.me/Vakansii_GetJob_bot'>бота</a></b>"
        )
        tags = "\n\n#вакансия #парсер"

        pretty_text = f"{header}{body_html}\n\n{contact_block}{instruction}{tags}"
        
        # НОВОЕ: Получаем ссылку на исходное сообщение
        message_link = message.link if hasattr(message, 'link') else None
        if message_link:
            print(f"🔗 Ссылка на исходное сообщение: {message_link}")
        
        # НОВОЕ: Для особых частов отправляем с флагом is_special=True
        send_to_moderation(TARGET_GROUP_ID, REPORT_TOPIC_ID, pretty_text, author_id, message_link, is_special=is_special)

async def main():
    print("🚀 Запуск парсера...")
    await app.start()
    try:
        await app.get_chat(TARGET_GROUP_ID)
        print(f"✅ Доступ к группе модерации подтвержден")
    except Exception as e:
        print(f"⚠️ Группа {TARGET_GROUP_ID} не доступна: {e}")
    
    print(f"📡 Мониторинг запущен.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        app.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Парсер остановлен")
    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")
        sys.exit(1)