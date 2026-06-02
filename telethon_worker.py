import asyncio
import sqlite3
import re
import html
import requests
import traceback
from telethon import TelegramClient

# ==================== НАСТРОЙКИ ====================
API_ID = 33481567
API_HASH = "93d073404049ef77e94be613d29fb57d"
BOT_TOKEN = "7941528893:AAFCMSzgUH3fuMc2cTXzKaPJKXTjZYXNkS4"
TARGET_GROUP_ID = -1003455134116
PROBLEM_CHAT_ID = -1001156193082
REPORT_TOPIC_ID = None

# ==================== КЛИЕНТ ====================
client = TelegramClient("telethon_worker", API_ID, API_HASH)

# ==================== ФУНКЦИИ РАБОТЫ С БД ====================
def get_special_chats():
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

def get_data_from_db():
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

# ==================== ОТПРАВКА В МОДЕРАЦИЮ ====================
def send_to_moderation(chat_id, thread_id, text, author_id=None, message_link=None, is_special=False):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    if is_special:
        keyboard = [[{"text": "⏳ Загрузка...", "callback_data": "loading"}]]
    else:
        keyboard = [
            [{"text": "✅ Опубликовать", "callback_data": "pub_approve"},
             {"text": "❌ Отклонить", "callback_data": "pub_decline"}]
        ]
        if message_link:
            keyboard.append([{"text": "🔗 Источник", "url": message_link}])
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": keyboard}
    }
    if thread_id:
        payload["message_thread_id"] = thread_id
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        res = r.json()
        
        if res.get("ok") and is_special:
            msg_id = res.get("result", {}).get("message_id")
            if msg_id:
                update_url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageReplyMarkup"
                buttons = []
                if message_link:
                    buttons.append({"text": "🔗 Источник", "url": message_link})
                buttons.append({"text": "✏️ Ввести контакт", "callback_data": f"edit_contact_{msg_id}"})
                buttons.append({"text": "✅ Опубликовать", "callback_data": f"pub_approve_special_{msg_id}"})
                buttons.append({"text": "❌ Отклонить", "callback_data": f"pub_decline_special_{msg_id}"})
                keyboard_rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
                update_payload = {
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "reply_markup": {"inline_keyboard": keyboard_rows}
                }
                requests.post(update_url, json=update_payload, timeout=10)
                print(f"✅ Кнопки для особого чата обновлены (message_id: {msg_id})")
        
        if not res.get("ok"):
            print(f"❌ Ошибка Telegram API: {res.get('description')}")
    except Exception as e:
        print(f"❌ Ошибка при отправке модератору: {e}")

# ==================== ОБРАБОТКА СООБЩЕНИЯ ====================
async def process_message(message):
    try:
        content = message.text or message.caption
        if not content:
            return
        
        channels_db, keywords, stop_words = get_data_from_db()
        msg_text_lower = content.lower()
        
        # Проверяем, отслеживается ли этот чат
        is_target = False
        cid_full = str(PROBLEM_CHAT_ID)
        cid_short = cid_full.replace("-100", "")
        
        for conf in channels_db:
            clean_conf = conf.replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '').strip()
            if (clean_conf == cid_full) or (clean_conf == cid_short):
                is_target = True
                break
        
        if not is_target:
            return
        
        # Стоп-слова
        for stop_word in stop_words:
            if stop_word and stop_word in msg_text_lower:
                print(f"🚫 Пропущено (стоп-слово): '{stop_word}'")
                return
        
        # Ключевые слова
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
        
        if not found_keyword:
            return
        
        # Получаем отправителя
        sender = await message.get_sender()
        contact = "Не указан"
        author_id = None
        has_username = False
        
        if sender:
            if sender.username:
                contact = f"@{sender.username}"
                author_id = sender.id
                has_username = True
                print(f"📱 Найден username: @{sender.username}")
            elif sender.first_name:
                contact = html.escape(sender.first_name)
                author_id = sender.id
                print(f"📱 Нет username, найдено имя: {contact}")
            else:
                contact = "Автор"
                author_id = sender.id
        
        is_special = not has_username
        
        # Формирование поста
        header = "<b>| 🇻 🇦 🇨 🇦 🇳 🇨 🇾 |</b>\n\n"
        body_html = html.escape(content)
        
        if not has_username:
            contact_block = f"<b>Контакт для связи:</b>\n<i>⚠️ Контакт не найден (укажите @username или добавьте контакт в текст)</i>\n\n"
        else:
            contact_block = f"<b>Контакт для связи:</b>\n{contact}\n\n"
        
        instruction = (
            "<b><code>Для публикации вакансии\\резюме, напишите заявку в </code>"
            "<a href='https://t.me/Vakansii_GetJob_bot'>бота</a></b>"
        )
        tags = "\n\n#вакансия #парсер"
        pretty_text = f"{header}{body_html}\n\n{contact_block}{instruction}{tags}"
        
        # Ссылка на сообщение
        message_link = None
        if str(PROBLEM_CHAT_ID).startswith("-100"):
            chat_id_for_link = str(PROBLEM_CHAT_ID)[4:]
            message_link = f"https://t.me/c/{chat_id_for_link}/{message.id}"
        
        send_to_moderation(TARGET_GROUP_ID, REPORT_TOPIC_ID, pretty_text, author_id, message_link, is_special=is_special)
        print(f"✅ Отправлено в модерацию: {message.id} (особый режим: {is_special})")
        
    except Exception as e:
        print(f"❌ Ошибка в process_message: {e}")
        traceback.print_exc()

# ==================== ПОЛЛИНГ ====================
async def main():
    print("🚀 Запуск Telethon-воркера для проблемного чата...")
    
    try:
        await client.start()
        print("✅ Клиент Telethon запущен")
    except Exception as e:
        print(f"❌ Ошибка запуска клиента: {e}")
        traceback.print_exc()
        return
    
    # Получаем сущность чата
    try:
        entity = await client.get_entity(PROBLEM_CHAT_ID)
        print(f"✅ Доступ к чату {PROBLEM_CHAT_ID} получен")
    except Exception as e:
        print(f"❌ Нет доступа к чату {PROBLEM_CHAT_ID}: {e}")
        traceback.print_exc()
        return
    
    last_id = 0
    
    while True:
        try:
            # Получаем последние 10 сообщений
            messages = await client.get_messages(entity, limit=10, min_id=last_id)
            
            for msg in reversed(messages):
                if msg.id > last_id:
                    await process_message(msg)
                    last_id = max(last_id, msg.id)
            
            await asyncio.sleep(30)
            
        except Exception as e:
            print(f"⚠️ Ошибка в цикле polling: {e}")
            traceback.print_exc()
            await asyncio.sleep(30)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Telethon-воркер остановлен")
    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")
        traceback.print_exc()