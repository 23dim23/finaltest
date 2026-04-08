import sqlite3
import asyncio
import re
import requests
import html
import sys
from pyrogram import Client, enums

# --- НАСТРОЙКИ ---
API_ID = 33481567 
API_HASH = "93d073404049ef77e94be613d29fb57d"
# Токен твоего актуального бота @your_shortsbot
BOT_TOKEN = "7941528893:AAFCMSzgUH3fuMc2cTXzKaPJKXTjZYXNkS4" 
# ID твоей группы из основного кода бота
TARGET_GROUP_ID = -1003455134116 
REPORT_TOPIC_ID = 1 

app = Client("my_account", api_id=API_ID, api_hash=API_HASH)

def get_data_from_db():
    try:
        conn = sqlite3.connect("parser_data.db")
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM channels")
        channels = [str(row[0]).strip().lower() for row in cursor.fetchall()]
        
        cursor.execute("SELECT word FROM keywords")
        keywords = [str(row[0]).lower().strip() for row in cursor.fetchall()]
        
        # ПОЛУЧЕНИЕ СТОП-СЛОВ
        cursor.execute("SELECT word FROM stop_words")
        stop_words = [str(row[0]).lower().strip() for row in cursor.fetchall()]
        
        conn.close()
        return channels, keywords, stop_words
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
        return [], [], []

def escape_html(text):
    """Экранирует спецсимволы, чтобы Telegram не выдавал ошибку разметки"""
    return html.escape(text)

# Функция для отправки сообщения с кнопками через Bot API с диагностикой
def send_to_moderation(chat_id, thread_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "message_thread_id": thread_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "✅ Опубликовать", "callback_data": "pub_approve"},
                    {"text": "❌ Отклонить", "callback_data": "pub_decline"}
                ]
            ]
        }
    }
    try:
        r = requests.post(url, json=payload)
        res = r.json()
        if res.get("ok"):
            print(f"✅ Пост успешно отправлен на модерацию в топик {thread_id}")
        else:
            print(f"❌ Ошибка Telegram API: {res.get('description')}")
            # Если ошибка в топике, пробуем отправить в общий чат группы
            if "thread not found" in str(res).lower():
                print("⚠️ Топик не найден, пробую отправить в общий чат...")
                payload.pop("message_thread_id")
                requests.post(url, json=payload)
    except Exception as e:
        print(f"❌ Критическая ошибка запроса: {e}")

@app.on_message()
async def check_messages(client, message):
    if not message.chat:
        return
    
    # Не парсим сообщения из нашей же группы модерации
    if message.chat.id == TARGET_GROUP_ID:
        return

    raw_topic_id = getattr(message, "message_thread_id", None)
    current_thread_id = str(raw_topic_id) if raw_topic_id else None

    content = message.text or message.caption
    if not content:
        return

    channels_db, keywords, stop_words = get_data_from_db()
    is_target = False
    msg_text_lower = content.lower()

    cid_full = str(message.chat.id)
    cid_short = cid_full.replace("-100", "")
    uname = message.chat.username.lower() if message.chat.username else ""

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

        chat_matches = (target_chat == uname) or (target_chat == cid_full) or (target_chat == cid_short)
        if chat_matches:
            if target_topic:
                if current_thread_id == target_topic:
                    is_target = True
                    break
            else:
                is_target = True
                break

    if is_target:
        # 1. ПРОВЕРКА НА СТОП-СЛОВА (Приоритет)
        for stop_word in stop_words:
            if stop_word in msg_text_lower:
                print(f"🚫 Сообщение пропущено: найдено стоп-слово '{stop_word}'")
                return # Выходим из функции, пост игнорируется полностью

        # 2. ПРОВЕРКА НА КЛЮЧЕВЫЕ СЛОВА
        for word in keywords:
            if word in msg_text_lower:
                # Поиск контактов
                found_usernames = re.findall(r"@[a-zA-Z0-9_]+", content)
                if found_usernames:
                    contact = found_usernames[0]
                else:
                    user = message.from_user
                    contact = f"@{user.username}" if user and user.username else "Не указан"

                # Формирование финального текста с экранированием
                header = "<b>🇻 🇦 🇨 🇦 🇳 🇨 🇾</b>\n\n"
                body = f"{escape_html(content.strip())}\n\n"
                contact_block = f"<b>Контакт для связи:</b>\n{contact}\n\n"
                instruction = (
                    "<b><code>Для публикации вакансии\\резюме, напишите заявку в </code>"
                    "<a href='https://t.me/Vakansii_GetJob_bot'>бота</a></b>"
                )
                tags = "\n\n#вакансия #монтаж"

                pretty_text = f"{header}{body}{contact_block}{instruction}{tags}"
                
                send_to_moderation(TARGET_GROUP_ID, REPORT_TOPIC_ID, pretty_text)
                break

async def main():
    print("🚀 Запуск парсера...")
    await app.start()
    
    global TARGET_GROUP_ID
    found = False

    # Принудительное обновление списка диалогов для устранения "Peer id invalid"
    print("🔍 Синхронизация диалогов...")
    async for dialog in app.get_dialogs():
        if dialog.chat.id == TARGET_GROUP_ID:
            print(f"✅ Целевая группа найдена: {dialog.chat.title}")
            found = True
            break
    
    if not found:
        # Если по ID не нашли, попробуем проверить прямой доступ
        try:
            chat = await app.get_chat(TARGET_GROUP_ID)
            print(f"✅ Группа доступна напрямую: {chat.title}")
        except Exception as e:
            print(f"⚠️ Ошибка доступа к группе {TARGET_GROUP_ID}: {e}")
            print("💡 Убедись, что твой аккаунт состоит в этой группе!")
    
    print(f"📡 Мониторинг запущен. Сообщения уходят в топик {REPORT_TOPIC_ID}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        app.run(main())
    except Exception as e:
        print(f"💥 Критическая ошибка в работе Pyrogram: {e}")
        # Выходим с кодом 1, чтобы main.py мог перезапустить скрипт
        sys.exit(1)