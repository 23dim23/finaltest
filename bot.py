import telebot
from telebot import types
import json
import os
import sqlite3
import re
from datetime import datetime, timedelta

# ==================== НАСТРОЙКИ ====================
TOKEN = '7941528893:AAFCMSzgUH3fuMc2cTXzKaPJKXTjZYXNkS4' 
SUPER_GROUP_ID = -1003455134116
ADMIN_ID = 5659638424 
DATA_FILE = 'user_threads.json'
SETTINGS_FILE = 'settings.json'
DB_FILE = 'parser_data.db' 

# Конфигурация каналов и их хэштегов
CHANNELS_CONFIG = {
    "🎥 Монтаж": {"channel": "@GetJob_videoedit", "tags": "\n\n#вакансия #монтаж"},
    "📱 SMM": {"channel": "@GetJob_smm", "tags": "\n\n#вакансия #smm"},
    "💻 IT/Разработка": {"channel": "@GetJob_IT", "tags": "\n\n#вакансия #IT"},
    "✍️ Копирайтинг": {"channel": "@GetJob_copyright", "tags": "\n\n#вакансия #копирайт"},
    "📊 Менеджмент": {"channel": "@GetJob_manager", "tags": "\n\n#вакансия #менеджер"},
    "🎨 Дизайн": {"channel": "@GetJob_design", "tags": "\n\n#вакансия #дизайн"}
}
# ===================================================

bot = telebot.TeleBot(TOKEN)

# Словарь для хранения временных данных при редактировании контакта
pending_contacts = {}

# --- РАБОТА С БАЗОЙ ДАННЫХ ПАРСЕРА ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Основные таблицы
    cursor.execute('CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY, url TEXT UNIQUE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS keywords (id INTEGER PRIMARY KEY, word TEXT UNIQUE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS stop_words (id INTEGER PRIMARY KEY, word TEXT UNIQUE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS special_chats (id INTEGER PRIMARY KEY, chat_id TEXT UNIQUE)')
    
    # Таблицы для рекомендаций
    cursor.execute('''CREATE TABLE IF NOT EXISTS recommend_settings (
        id INTEGER PRIMARY KEY, 
        button_text TEXT, 
        is_enabled INTEGER DEFAULT 0,
        show_stats INTEGER DEFAULT 1,
        select_category_text TEXT,
        select_specialist_text TEXT
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS recommend_categories (
        id INTEGER PRIMARY KEY, 
        name TEXT, 
        icon TEXT, 
        sort_order INTEGER DEFAULT 0
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS recommend_cards (
        id INTEGER PRIMARY KEY, 
        category_id INTEGER, 
        custom_text TEXT,
        contact TEXT, 
        photo_file_id TEXT,
        is_active INTEGER DEFAULT 1, 
        is_hot INTEGER DEFAULT 0, 
        views INTEGER DEFAULT 0, 
        clicks INTEGER DEFAULT 0, 
        sort_order INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS recommend_stats (
        id INTEGER PRIMARY KEY, 
        card_id INTEGER, 
        views INTEGER DEFAULT 0, 
        clicks INTEGER DEFAULT 0, 
        date DATE
    )''')
    
    # Добавляем настройки по умолчанию
    cursor.execute("SELECT COUNT(*) FROM recommend_settings")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO recommend_settings (button_text, is_enabled, show_stats, select_category_text, select_specialist_text) VALUES (?, ?, ?, ?, ?)",
                       ("⭐ GetJob рекомендует", 0, 1, "⭐ GetJob рекомендует\n\nВыберите категорию специалистов:", "⭐ GetJob рекомендует\n\nВыберите специалиста:"))
    
    # Добавляем столбец photo_file_id если его нет
    try:
        cursor.execute("ALTER TABLE recommend_cards ADD COLUMN photo_file_id TEXT")
    except:
        pass
    
    conn.commit()
    conn.close()
    print("✅ База данных готова")

init_db()

def get_db_items(table):
    allowed_tables = ['channels', 'keywords', 'stop_words', 'special_chats']
    if table not in allowed_tables:
        return []
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    if table == 'special_chats':
        col = 'chat_id'
    else:
        col = "url" if table == "channels" else "word"
    
    cursor.execute(f'SELECT id, {col} FROM {table}')
    items = cursor.fetchall()
    conn.close()
    return items

def add_db_item(table, value):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        if table == 'special_chats':
            col = 'chat_id'
            val = value.strip()
        else:
            col = "url" if table == "channels" else "word"
            val = value.strip().lower()
        
        cursor.execute(f'INSERT INTO {table} ({col}) VALUES (?)', (val,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка БД (add): {e}")
        return False

def delete_db_item(table, item_id):
    allowed_tables = ['channels', 'keywords', 'stop_words', 'special_chats']
    if table not in allowed_tables:
        return False
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(f'DELETE FROM {table} WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка БД (del): {e}")
        return False

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ РЕКОМЕНДАЦИЙ ---
def get_recommend_settings():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT button_text, is_enabled, show_stats, select_category_text, select_specialist_text FROM recommend_settings LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"button_text": row[0], "is_enabled": row[1], "show_stats": row[2], "select_category_text": row[3], "select_specialist_text": row[4]}
    return {"button_text": "⭐ GetJob рекомендует", "is_enabled": 0, "show_stats": 1, "select_category_text": "⭐ GetJob рекомендует\n\nВыберите категорию специалистов:", "select_specialist_text": "⭐ GetJob рекомендует\n\nВыберите специалиста:"}

def update_recommend_settings(button_text=None, is_enabled=None, show_stats=None, select_category_text=None, select_specialist_text=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    if button_text is not None:
        cursor.execute("UPDATE recommend_settings SET button_text = ?", (button_text,))
    if is_enabled is not None:
        cursor.execute("UPDATE recommend_settings SET is_enabled = ?", (is_enabled,))
    if show_stats is not None:
        cursor.execute("UPDATE recommend_settings SET show_stats = ?", (show_stats,))
    if select_category_text is not None:
        cursor.execute("UPDATE recommend_settings SET select_category_text = ?", (select_category_text,))
    if select_specialist_text is not None:
        cursor.execute("UPDATE recommend_settings SET select_specialist_text = ?", (select_specialist_text,))
    conn.commit()
    conn.close()

def get_categories():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, icon, sort_order FROM recommend_categories ORDER BY sort_order")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "icon": r[2], "sort_order": r[3]} for r in rows]

def add_category(name, icon="📁"):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO recommend_categories (name, icon) VALUES (?, ?)", (name, icon))
    conn.commit()
    conn.close()

def delete_category(cat_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM recommend_categories WHERE id = ?", (cat_id,))
    cursor.execute("DELETE FROM recommend_cards WHERE category_id = ?", (cat_id,))
    conn.commit()
    conn.close()

def get_cards_by_category(category_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, custom_text, contact, photo_file_id, is_active, is_hot, views, clicks, sort_order FROM recommend_cards WHERE category_id = ? AND is_active = 1 ORDER BY is_hot DESC, sort_order", (category_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "custom_text": r[1], "contact": r[2], "photo_file_id": r[3], "is_active": r[4], "is_hot": r[5], "views": r[6], "clicks": r[7], "sort_order": r[8]} for r in rows]

def get_card_by_id(card_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, category_id, custom_text, contact, photo_file_id, is_active, is_hot, views, clicks, sort_order FROM recommend_cards WHERE id = ?", (card_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "category_id": row[1], "custom_text": row[2], "contact": row[3], "photo_file_id": row[4], "is_active": row[5], "is_hot": row[6], "views": row[7], "clicks": row[8], "sort_order": row[9]}
    return None

def add_card(category_id, custom_text, contact, photo_file_id=None, is_hot=0):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO recommend_cards (category_id, custom_text, contact, photo_file_id, is_hot) VALUES (?, ?, ?, ?, ?)",
                   (category_id, custom_text, contact, photo_file_id, is_hot))
    conn.commit()
    conn.close()

def update_card(card_id, **kwargs):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for key, value in kwargs.items():
        cursor.execute(f"UPDATE recommend_cards SET {key} = ? WHERE id = ?", (value, card_id))
    conn.commit()
    conn.close()

def delete_card(card_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM recommend_cards WHERE id = ?", (card_id,))
    conn.commit()
    conn.close()

def increment_views(card_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE recommend_cards SET views = views + 1 WHERE id = ?", (card_id,))
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("INSERT INTO recommend_stats (card_id, views, clicks, date) VALUES (?, 1, 0, ?)", (card_id, today))
    conn.commit()
    conn.close()

def increment_clicks(card_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE recommend_cards SET clicks = clicks + 1 WHERE id = ?", (card_id,))
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("INSERT INTO recommend_stats (card_id, views, clicks, date) VALUES (?, 0, 1, ?)", (card_id, today))
    conn.commit()
    conn.close()

def update_hot_status():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT card_id, SUM(clicks) as total_clicks 
        FROM recommend_stats 
        WHERE date >= ? 
        GROUP BY card_id 
        ORDER BY total_clicks DESC 
        LIMIT 3
    """, (week_ago,))
    top_cards = [row[0] for row in cursor.fetchall()]
    
    cursor.execute("UPDATE recommend_cards SET is_hot = 0")
    for card_id in top_cards:
        cursor.execute("UPDATE recommend_cards SET is_hot = 1 WHERE id = ?", (card_id,))
    conn.commit()
    conn.close()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return default
    return default

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

DEFAULT_SETTINGS = {
    "pay_rf": "💳 <b>Карта РФ (СБП):</b>\n<code>0000 0000 0000 0000</code>\nПолучатель: Иван И.",
    "pay_rb": "🇧🇾 <b>Карта РБ:</b>\n<code>0000 0000 0000 0000</code>\nПолучатель: Иван И.",
    "pay_crypto": "₿ <b>USDT (TRC20):</b>\n<code>ВАШ_КОШЕЛЕК</code> ",
    "price_standard": "250",
    "price_fast": "300",
    "price_ad": "500",
    "logging_enabled": True,
    "txt_start": "👋 Здравствуйте! Выберите нужный раздел:",
    "txt_vacancy_instr": "📋 <b>Публикация вакансии</b>\nПришлите текст объявления одним сообщением:",
    "txt_resume_instr": "👤 <b>Публикация резюме</b>\nПришлите текст объявления одним сообщением:",
    "txt_admin_chat": "✉️ <b>Режим связи с модератором.</b>\nНапишите ваш вопрос ниже:",
    "txt_ad_info": "📢 <b>Реклама</b>\nСвяжитесь с модератором напрямую для уточнения деталей.",
    "txt_wait_time": "📅 Принято! Напишите желаемое время публикации:",
    "txt_wait_check": "⚠️ <b>Пришлите скриншот чека ниже:</b>",
    "txt_success_pay": "⏳ Чек принят. Ожидайте подтверждения модератором!",
    "txt_ad_banner": "🌟 <b>Реклама:</b> Подписывайтесь на наш основной канал!",
    "txt_ad_btn_name": "Перейти в канал",
    "txt_ad_btn_url": "https://t.me/your_channel",
    "ad_frequency": "5",
    "ad_button_enabled": True
}

current_settings = load_json(SETTINGS_FILE, DEFAULT_SETTINGS)

def safe_send_message(chat_id, text, **kwargs):
    try:
        return bot.send_message(chat_id, text, parse_mode='HTML', **kwargs)
    except:
        return bot.send_message(chat_id, text, parse_mode=None, **kwargs)

def log_action(user_id, action_text):
    if not current_settings.get("logging_enabled", True): return
    user_threads = load_json(DATA_FILE, {})
    thread_id = user_threads.get(str(user_id), {}).get("thread_id")
    if thread_id:
        try: bot.send_message(SUPER_GROUP_ID, f"🔍 <b>Действие:</b> {action_text}", message_thread_id=thread_id, parse_mode='HTML')
        except: pass

def check_and_send_ad(chat_id):
    user_threads = load_json(DATA_FILE, {})
    if chat_id not in user_threads: return
    
    count = user_threads[chat_id].get("msg_count", 0) + 1
    user_threads[chat_id]["msg_count"] = count
    save_json(DATA_FILE, user_threads)
    
    freq = int(current_settings.get("ad_frequency", 5))
    
    if count % freq == 0:
        ad_text = current_settings.get("txt_ad_banner", "")
        if not ad_text: return

        markup = None
        if current_settings.get("ad_button_enabled", True):
            btn_name = current_settings.get("txt_ad_btn_name", "Открыть")
            btn_url = current_settings.get("txt_ad_btn_url", "")
            if btn_url:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(btn_name, url=btn_url))
        
        try:
            bot.send_message(chat_id, f"📢 {ad_text}", parse_mode='HTML', reply_markup=markup)
        except: pass

# ==================== КЛАВИАТУРЫ ====================

def get_reply_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🏠 Главное меню"))
    return markup

def get_main_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    buttons = [
        types.InlineKeyboardButton("📋 Опубликовать вакансию", callback_data="vacancy"),
        types.InlineKeyboardButton("👤 Опубликовать резюме", callback_data="resume"),
        types.InlineKeyboardButton("📢 Опубликовать рекламу", callback_data="ad"),
        types.InlineKeyboardButton("✉️ Связаться с модератором", callback_data="admin_chat")
    ]
    settings = get_recommend_settings()
    if settings["is_enabled"]:
        buttons.append(types.InlineKeyboardButton(settings["button_text"], callback_data="show_recommends"))
    markup.add(*buttons)
    return markup

def get_nav_menu(back_callback="main_menu"):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Назад", callback_data=back_callback),
        types.InlineKeyboardButton("🏠 В меню", callback_data="main_menu")
    )
    return markup

def get_user_info_btn(user_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("👤 Инфо о пользователе", callback_data=f"user_info_{user_id}"))
    return markup

def get_admin_panel_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    log_status = "✅ Логи: ВКЛ" if current_settings.get("logging_enabled", True) else "❌ Логи: ВЫКЛ"
    markup.add(
        types.InlineKeyboardButton("💰 ЦЕНЫ", callback_data="adm_prices"),
        types.InlineKeyboardButton("💳 РЕКВИЗИТЫ", callback_data="adm_pay"),
        types.InlineKeyboardButton("📝 ТЕКСТЫ", callback_data="adm_texts"),
        types.InlineKeyboardButton("📢 УПР. РЕКЛАМОЙ (ПЛАШКИ)", callback_data="adm_ads"),
        types.InlineKeyboardButton("📡 УПРАВЛЕНИЕ ПАРСЕРОМ", callback_data="adm_parser"),
        types.InlineKeyboardButton("⭐ УПРАВЛЕНИЕ РЕКОМЕНДАЦИЯМИ", callback_data="adm_recommends"),
        types.InlineKeyboardButton(log_status, callback_data="toggle_logging"),
        types.InlineKeyboardButton("🔙 Закрыть", callback_data="main_menu")
    )
    return markup

def get_admin_ad_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    ad_btn_status = "🔘 Кнопка в плашке: ВКЛ" if current_settings.get("ad_button_enabled", True) else "⚪️ Кнопка в плашке: ВЫКЛ"
    markup.add(
        types.InlineKeyboardButton("📝 Текст плашки", callback_data="edit_txt_ad_banner"),
        types.InlineKeyboardButton("🔢 Частота (сообщ.)", callback_data="edit_ad_frequency"),
        types.InlineKeyboardButton("🏷 Текст кнопки", callback_data="edit_txt_ad_btn_name"),
        types.InlineKeyboardButton("🔗 Ссылка кнопки", callback_data="edit_txt_ad_btn_url"),
        types.InlineKeyboardButton(ad_btn_status, callback_data="toggle_ad_button"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")
    )
    return markup

def get_parser_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📢 КАНАЛЫ (Источники)", callback_data="parser_channels"),
        types.InlineKeyboardButton("🔑 КЛЮЧЕВЫЕ СЛОВА", callback_data="parser_keywords"),
        types.InlineKeyboardButton("🚫 СТОП-СЛОВА", callback_data="parser_stop_words"),
        types.InlineKeyboardButton("🔧 ОСОБЫЕ ЧАТЫ", callback_data="parser_special_chats"),
        types.InlineKeyboardButton("🔙 Назад в админку", callback_data="admin_panel")
    )
    return markup

def get_db_manage_markup(table):
    markup = types.InlineKeyboardMarkup(row_width=1)
    items = get_db_items(table)
    
    for item_id, val in items:
        display_text = val
        if table == 'special_chats':
            try:
                chat = bot.get_chat(int(val))
                chat_name = chat.title or chat.first_name
                display_text = f"{chat_name} ({val})"
            except:
                display_text = val
        markup.add(types.InlineKeyboardButton(f"❌ Удалить: {display_text}", callback_data=f"del_{table}_{item_id}"))
    
    markup.add(types.InlineKeyboardButton("➕ Добавить", callback_data=f"add_{table}"))
    markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="adm_parser"))
    return markup

def get_admin_prices_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"Стандарт ({current_settings.get('price_standard')}₽)", callback_data="edit_price_standard"),
        types.InlineKeyboardButton(f"Закреп ({current_settings.get('price_fast')}₽)", callback_data="edit_price_fast"),
        types.InlineKeyboardButton(f"Реклама ({current_settings.get('price_ad')}₽)", callback_data="edit_price_ad"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")
    )
    return markup

def get_admin_pay_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("Реквизиты РФ", callback_data="edit_pay_rf"),
        types.InlineKeyboardButton("Реквизиты РБ", callback_data="edit_pay_rb"),
        types.InlineKeyboardButton("Реквизиты Крипто", callback_data="edit_pay_crypto"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")
    )
    return markup

def get_admin_texts_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("Старт", callback_data="edit_txt_start"),
        types.InlineKeyboardButton("Инстр. Вакансия", callback_data="edit_txt_vacancy_instr"),
        types.InlineKeyboardButton("Инстр. Резюме", callback_data="edit_txt_resume_instr"),
        types.InlineKeyboardButton("Инстр. Реклама", callback_data="edit_txt_ad_info"),
        types.InlineKeyboardButton("Запрос времени", callback_data="edit_txt_wait_time"),
        types.InlineKeyboardButton("Запрос чека", callback_data="edit_txt_wait_check"),
        types.InlineKeyboardButton("Успех оплаты", callback_data="edit_txt_success_pay"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")
    )
    return markup

def get_tariff_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    p_std = current_settings.get("price_standard", "0")
    p_fast = current_settings.get("price_fast", "300")
    markup.add(
        types.InlineKeyboardButton(f"Обычная ({p_std} ₽)", callback_data="set_tariff_standard"),
        types.InlineKeyboardButton(f"🔥 С закрепом ({p_fast} ₽)", callback_data="set_tariff_fast"),
        types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_text"),
        types.InlineKeyboardButton("🏠 В меню", callback_data="main_menu")
    )
    return markup

def get_payment_choice_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💳 Карта РФ", callback_data="pay_rf"),
        types.InlineKeyboardButton("🇧🇾 Карта РБ", callback_data="pay_rb"),
        types.InlineKeyboardButton("₿ Криптовалюта", callback_data="pay_crypto"),
        types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_tariff"),
        types.InlineKeyboardButton("🏠 В меню", callback_data="main_menu")
    )
    return markup

def get_cancel_menu():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Отменить и в меню", callback_data="main_menu"))
    return markup

def get_cancel_parser_menu():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Отменить", callback_data="adm_parser"))
    return markup

def get_moderator_decision_markup(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f"mod_approve_{user_id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"mod_decline_{user_id}"),
        types.InlineKeyboardButton("👤 Инфо", callback_data=f"user_info_{user_id}")
    )
    return markup

def get_special_moderation_markup(message_id, message_link=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("✏️ Ввести контакт", callback_data=f"edit_contact_{message_id}"),
        types.InlineKeyboardButton("✅ Опубликовать", callback_data=f"pub_approve_special_{message_id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"pub_decline_special_{message_id}")
    ]
    if message_link:
        buttons.insert(0, types.InlineKeyboardButton("🔗 Источник", url=message_link))
    markup.add(*buttons)
    return markup

def get_special_moderation_after_edit_markup(message_id, message_link=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("✅ Опубликовать", callback_data=f"pub_approve_special_{message_id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"pub_decline_special_{message_id}"),
        types.InlineKeyboardButton("🔄 Изменить контакт", callback_data=f"edit_contact_{message_id}")
    ]
    if message_link:
        buttons.insert(0, types.InlineKeyboardButton("🔗 Источник", url=message_link))
    markup.add(*buttons)
    return markup

# ==================== ЛОГИКА ШАГОВ (STEPS) ====================

def process_db_add(message, table):
    chat_id = str(message.chat.id)
    if message.text and message.text.startswith('/'): return
    
    if add_db_item(table, message.text):
        bot.send_message(chat_id, "✅ Успешно добавлено в базу!")
    else:
        bot.send_message(chat_id, "❌ Ошибка при добавлении (возможно, уже есть).")
    
    user_threads = load_json(DATA_FILE, {})
    if chat_id in user_threads:
        user_threads[chat_id]["state"] = None
        save_json(DATA_FILE, user_threads)
    
    bot.send_message(chat_id, f"📡 Меню управления: {table}", reply_markup=get_db_manage_markup(table))

def save_new_setting(message, key):
    chat_id = str(message.chat.id)
    if message.text == '/start' or message.text == '/admin_panel': return

    current_settings[key] = message.text
    save_json(SETTINGS_FILE, current_settings)
    
    user_threads = load_json(DATA_FILE, {})
    if chat_id in user_threads:
        user_threads[chat_id]["state"] = None
        save_json(DATA_FILE, user_threads)

    if key.startswith("txt_ad_") or key == "ad_frequency":
        bot.send_message(chat_id, "✅ Настройка рекламы сохранена!", reply_markup=get_admin_ad_markup())
    else:
        safe_send_message(chat_id, f"✅ Обновлено!", reply_markup=get_admin_panel_markup())

def process_submission_time(message, user_data):
    chat_id = str(message.chat.id)
    if message.text and message.text.startswith('/'): return
    
    user_threads = load_json(DATA_FILE, {})
    user_threads[chat_id]["state"] = "waiting_tariff"
    save_json(DATA_FILE, user_threads)

    log_action(chat_id, f"Указал время: <code>{message.text}</code>")
    bot.send_message(SUPER_GROUP_ID, f"⏰ <b>Желаемое время:</b> {message.text}", message_thread_id=user_data["thread_id"], parse_mode='HTML')
    bot.send_message(chat_id, "💎 Выберите тип размещения:", reply_markup=get_tariff_menu())

def wait_for_screenshot(message, user_data):
    chat_id = str(message.chat.id)
    if message.text and message.text.startswith('/'): return
    
    user_threads = load_json(DATA_FILE, {})
    if user_threads.get(chat_id, {}).get("state") != "waiting_screenshot":
        return

    if message.content_type != 'photo':
        msg = bot.send_message(chat_id, "❌ Ошибка! Нужно фото чека.", reply_markup=get_nav_menu("back_to_payment_choice"))
        bot.register_next_step_handler(msg, wait_for_screenshot, user_data)
        return
    
    tariff_label = "🔥 ЗАКРЕП" if user_data.get("tariff") == "fast" else "⚪️ ОБЫЧНАЯ"
    bot.send_message(SUPER_GROUP_ID, 
                     f"💳 <b>ПРИСЛАН ЧЕК</b>\nТариф: {tariff_label}\nОтправитель: {message.from_user.first_name}", 
                     message_thread_id=user_data["thread_id"], 
                     parse_mode='HTML',
                     reply_markup=get_moderator_decision_markup(chat_id))
    
    bot.copy_message(SUPER_GROUP_ID, chat_id, message.message_id, message_thread_id=user_data["thread_id"])
    
    success_text = current_settings.get("txt_success_pay") or "⏳ Чек принят."
    safe_send_message(chat_id, success_text, reply_markup=get_main_menu())
    
    user_threads = load_json(DATA_FILE, {})
    user_threads[chat_id].update({"state": None, "type": "chat", "tariff": None})
    save_json(DATA_FILE, user_threads)

# ==================== ОБРАБОТЧИК CALLBACK ====================

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    print(f"🔔 ПОЛУЧЕН CALLBACK: {call.data}")
    chat_id = str(call.message.chat.id)
    data = call.data
    
    bot.clear_step_handler_by_chat_id(chat_id)
    
    user_threads = load_json(DATA_FILE, {})
    if chat_id not in user_threads: user_threads[chat_id] = {}

    # Обработка рекомендаций
    if data == "show_recommends":
        categories = get_categories()
        settings = get_recommend_settings()
        if not categories:
            bot.send_message(chat_id, "📭 Пока нет доступных категорий.", reply_markup=get_nav_menu())
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for cat in categories:
            count = len(get_cards_by_category(cat["id"]))
            markup.add(types.InlineKeyboardButton(f"{cat['icon']} {cat['name']} ({count})", callback_data=f"cat_{cat['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="main_menu"))
        bot.send_message(chat_id, settings["select_category_text"], reply_markup=markup, parse_mode='HTML')
        return

    if data.startswith("cat_"):
        cat_id = int(data.replace("cat_", ""))
        cards = get_cards_by_category(cat_id)
        settings = get_recommend_settings()
        if not cards:
            bot.send_message(chat_id, "📭 В этой категории пока нет специалистов.", reply_markup=get_nav_menu("show_recommends"))
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for card in cards:
            hot_icon = "🔥 " if card["is_hot"] else ""
            markup.add(types.InlineKeyboardButton(f"{hot_icon}{card['custom_text'].split(chr(10))[0][:30]}", callback_data=f"card_{card['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="show_recommends"))
        bot.send_message(chat_id, settings["select_specialist_text"], reply_markup=markup, parse_mode='HTML')
        return

    if data.startswith("card_"):
        card_id = int(data.replace("card_", ""))
        card = get_card_by_id(card_id)
        if not card:
            bot.answer_callback_query(call.id, "Карточка не найдена")
            return
        
        increment_views(card_id)
        
        hot_icon = "🔥 " if card["is_hot"] else ""
        settings = get_recommend_settings()
        
        text = f"{hot_icon}{card['custom_text']}"
        
        if settings["show_stats"]:
            views_word = "просмотр" if card['views'] % 10 == 1 and card['views'] % 100 != 11 else "просмотра" if 2 <= card['views'] % 10 <= 4 and not (12 <= card['views'] % 100 <= 14) else "просмотров"
            clicks_word = "переход" if card['clicks'] % 10 == 1 and card['clicks'] % 100 != 11 else "перехода" if 2 <= card['clicks'] % 10 <= 4 and not (12 <= card['clicks'] % 100 <= 14) else "переходов"
            text += f"\n\n📊 Статистика: {card['views']} {views_word}, {card['clicks']} {clicks_word}"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✉️ Связаться", callback_data=f"contact_{card_id}"),
            types.InlineKeyboardButton("⬅️ Назад", callback_data=f"cat_{card['category_id']}"),
            types.InlineKeyboardButton("🏠 В меню", callback_data="main_menu")
        )
        
        if card.get("photo_file_id"):
            bot.send_photo(chat_id, card["photo_file_id"], caption=text, reply_markup=markup, parse_mode='HTML')
        else:
            bot.send_message(chat_id, text, reply_markup=markup, parse_mode='HTML')
        return

    if data.startswith("contact_"):
        card_id = int(data.replace("contact_", ""))
        card = get_card_by_id(card_id)
        if card and card["contact"]:
            increment_clicks(card_id)
            update_hot_status()
            contact = card["contact"]
            if not contact.startswith('@'):
                contact = '@' + contact
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✉️ Открыть чат", url=f"https://t.me/{contact[1:]}"))
            markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data=f"card_{card_id}"))
            bot.send_message(chat_id, f"✉️ <b>Контакт специалиста:</b>\n\n{contact}", reply_markup=markup, parse_mode='HTML')
        else:
            bot.answer_callback_query(call.id, "Контакт не указан")
        bot.answer_callback_query(call.id)
        return

    # Админ-панель рекомендаций
    if data == "adm_recommends":
        settings = get_recommend_settings()
        status_text = "🟢 ВКЛ" if settings["is_enabled"] else "🔴 ВЫКЛ"
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"🔘 Отображение: {status_text}", callback_data="toggle_recommends"),
            types.InlineKeyboardButton("📝 Текст кнопки", callback_data="edit_recommend_button"),
            types.InlineKeyboardButton("📝 Текст 'Выберите категорию'", callback_data="edit_select_category_text"),
            types.InlineKeyboardButton("📝 Текст 'Выберите специалиста'", callback_data="edit_select_specialist_text"),
            types.InlineKeyboardButton("📊 Показать статистику", callback_data="recommend_stats"),
            types.InlineKeyboardButton("🗂️ Управление категориями", callback_data="manage_categories"),
            types.InlineKeyboardButton("👤 Управление карточками", callback_data="manage_cards"),
            types.InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")
        )
        bot.send_message(chat_id, "⭐ <b>Управление рекомендациями</b>\n\nЗдесь вы можете настроить раздел 'GetJob рекомендует'", reply_markup=markup, parse_mode='HTML')
        return

    if data == "toggle_recommends":
        settings = get_recommend_settings()
        update_recommend_settings(is_enabled=1 if not settings["is_enabled"] else 0)
        status_text = "🟢 ВКЛ" if not settings["is_enabled"] else "🔴 ВЫКЛ"
        bot.answer_callback_query(call.id, f"Отображение {status_text}")
        callback_handler(call)
        return

    if data == "edit_recommend_button":
        user_threads[chat_id]["state"] = "editing_recommend_button"
        save_json(DATA_FILE, user_threads)
        msg = bot.send_message(chat_id, "✍️ Введите новый текст для кнопки:\n\nТекущий: " + get_recommend_settings()["button_text"], reply_markup=get_cancel_menu())
        bot.register_next_step_handler(msg, save_recommend_button_text)
        return

    if data == "edit_select_category_text":
        user_threads[chat_id]["state"] = "editing_select_category_text"
        save_json(DATA_FILE, user_threads)
        msg = bot.send_message(chat_id, "✍️ Введите новый текст для страницы 'Выберите категорию':\n\nТекущий:\n" + get_recommend_settings()["select_category_text"], reply_markup=get_cancel_menu())
        bot.register_next_step_handler(msg, save_select_category_text)
        return

    if data == "edit_select_specialist_text":
        user_threads[chat_id]["state"] = "editing_select_specialist_text"
        save_json(DATA_FILE, user_threads)
        msg = bot.send_message(chat_id, "✍️ Введите новый текст для страницы 'Выберите специалиста':\n\nТекущий:\n" + get_recommend_settings()["select_specialist_text"], reply_markup=get_cancel_menu())
        bot.register_next_step_handler(msg, save_select_specialist_text)
        return

    if data == "recommend_stats":
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM recommend_cards")
        total_cards = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(views), SUM(clicks) FROM recommend_cards")
        total_views, total_clicks = cursor.fetchone()
        total_views = total_views or 0
        total_clicks = total_clicks or 0
        conversion = (total_clicks / total_views * 100) if total_views > 0 else 0
        
        cursor.execute("SELECT custom_text, views, clicks FROM recommend_cards ORDER BY clicks DESC LIMIT 5")
        top_cards = cursor.fetchall()
        conn.close()
        
        text = f"📊 <b>Статистика рекомендаций</b>\n\n"
        text += f"📋 Всего карточек: {total_cards}\n"
        text += f"👁️ Всего просмотров: {total_views}\n"
        text += f"✉️ Всего контактов: {total_clicks}\n"
        text += f"📈 Конверсия: {conversion:.1f}%\n\n"
        text += "<b>🏆 ТОП-5 карточек по контактам:</b>\n"
        for i, (custom_text, views, clicks) in enumerate(top_cards, 1):
            name = custom_text.split(chr(10))[0][:30]
            text += f"{i}. {name} - {clicks} контактов ({views} просмотров)\n"
        
        bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=get_nav_menu("adm_recommends"))
        return

    if data == "manage_categories":
        categories = get_categories()
        text = "🗂️ <b>Управление категориями</b>\n\n"
        for cat in categories:
            text += f"{cat['icon']} {cat['name']} (ID: {cat['id']})\n"
        text += "\nИспользуйте кнопки ниже для управления:"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("➕ Добавить категорию", callback_data="add_category"),
            types.InlineKeyboardButton("❌ Удалить категорию", callback_data="del_category"),
            types.InlineKeyboardButton("🔙 Назад", callback_data="adm_recommends")
        )
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='HTML')
        return

    if data == "add_category":
        user_threads[chat_id]["state"] = "adding_category"
        save_json(DATA_FILE, user_threads)
        msg = bot.send_message(chat_id, "✍️ Введите название категории (можно со смайликом):\n\nПример: 🎥 Монтаж", reply_markup=get_cancel_menu())
        bot.register_next_step_handler(msg, add_category_step)
        return

    if data == "del_category":
        categories = get_categories()
        if not categories:
            bot.answer_callback_query(call.id, "Нет категорий для удаления")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for cat in categories:
            markup.add(types.InlineKeyboardButton(f"❌ {cat['icon']} {cat['name']}", callback_data=f"del_cat_{cat['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="manage_categories"))
        bot.send_message(chat_id, "🗑️ Выберите категорию для удаления:", reply_markup=markup, parse_mode='HTML')
        return

    if data.startswith("del_cat_"):
        cat_id = int(data.replace("del_cat_", ""))
        delete_category(cat_id)
        bot.answer_callback_query(call.id, "Категория удалена")
        callback_handler(call)
        return

    if data == "manage_cards":
        categories = get_categories()
        if not categories:
            bot.answer_callback_query(call.id, "Сначала создайте категорию")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for cat in categories:
            markup.add(types.InlineKeyboardButton(f"📋 {cat['icon']} {cat['name']}", callback_data=f"cards_cat_{cat['id']}"))
        markup.add(types.InlineKeyboardButton("➕ Добавить карточку", callback_data="add_card"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="adm_recommends"))
        bot.send_message(chat_id, "👤 Выберите категорию для управления карточками:", reply_markup=markup, parse_mode='HTML')
        return

    if data.startswith("cards_cat_"):
        cat_id = int(data.replace("cards_cat_", ""))
        cards = get_cards_by_category(cat_id)
        text = f"📋 <b>Карточки в категории</b>\n\n"
        for card in cards:
            hot = "🔥 " if card["is_hot"] else ""
            text += f"{hot}{card['custom_text'].split(chr(10))[0][:40]} (👁️{card['views']} ✉️{card['clicks']})\n"
        text += "\nИспользуйте кнопки ниже:"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("➕ Добавить", callback_data=f"add_card_to_{cat_id}"),
            types.InlineKeyboardButton("❌ Удалить", callback_data=f"del_card_from_{cat_id}"),
            types.InlineKeyboardButton("🔙 Назад", callback_data="manage_cards")
        )
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='HTML')
        return

    if data.startswith("add_card_to_"):
        cat_id = int(data.replace("add_card_to_", ""))
        user_threads[chat_id]["state"] = f"adding_card_{cat_id}"
        user_threads[chat_id]["temp_category"] = cat_id
        save_json(DATA_FILE, user_threads)
        
        msg = bot.send_message(chat_id, "✍️ Введите текст карточки (можно использовать HTML-разметку):\n\n"
                               "Пример:\n"
                               "<b>Иван Иванов</b>\n"
                               "🎥 Монтажер | 5 лет опыта\n"
                               "Специализация: свадебный монтаж, reels\n"
                               "Портфолио: t.me/portfolio\n"
                               "Стоимость: от 5000₽", reply_markup=get_cancel_menu())
        bot.register_next_step_handler(msg, add_card_text_step)
        return

    if data.startswith("del_card_from_"):
        cat_id = int(data.replace("del_card_from_", ""))
        cards = get_cards_by_category(cat_id)
        if not cards:
            bot.answer_callback_query(call.id, "Нет карточек для удаления")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for card in cards:
            markup.add(types.InlineKeyboardButton(f"❌ {card['custom_text'].split(chr(10))[0][:30]}", callback_data=f"del_card_{card['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data=f"cards_cat_{cat_id}"))
        bot.send_message(chat_id, "🗑️ Выберите карточку для удаления:", reply_markup=markup, parse_mode='HTML')
        return

    if data.startswith("del_card_"):
        card_id = int(data.replace("del_card_", ""))
        delete_card(card_id)
        bot.answer_callback_query(call.id, "Карточка удалена")
        callback_handler(call)
        return

    if data == "add_card":
        categories = get_categories()
        markup = types.InlineKeyboardMarkup(row_width=1)
        for cat in categories:
            markup.add(types.InlineKeyboardButton(f"{cat['icon']} {cat['name']}", callback_data=f"add_card_to_{cat['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="manage_cards"))
        bot.send_message(chat_id, "➕ Выберите категорию для добавления карточки:", reply_markup=markup, parse_mode='HTML')
        return

    # Остальные обработчики
    if data.startswith("user_info_"):
        u_id = data.replace("user_info_", "")
        try:
            u_chat = bot.get_chat(u_id)
            info = (f"👤 <b>ИНФО:</b>\n🆔 ID: <code>{u_id}</code>\n📛: {u_chat.first_name}\n🏷: @{u_chat.username}\n📝: {u_chat.bio}\n🔗 <a href='tg://user?id={u_id}'>Профиль</a>")
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, info, message_thread_id=call.message.message_thread_id, parse_mode='HTML')
        except: bot.answer_callback_query(call.id, "Ошибка получения данных", show_alert=True)
        return

    if data.startswith("edit_contact_"):
        original_message_id = int(data.replace("edit_contact_", ""))
        
        print(f"🔧 Обработка edit_contact для message_id={original_message_id}")
        
        message_link = None
        if call.message.reply_markup:
            try:
                for row in call.message.reply_markup.keyboard:
                    for btn in row:
                        if hasattr(btn, 'url') and btn.url and "t.me" in btn.url:
                            message_link = btn.url
                            print(f"🔧 Найдена ссылка: {message_link}")
                            break
            except Exception as e:
                print(f"Ошибка при поиске ссылки: {e}")
        
        pending_contacts[original_message_id] = {
            "original_text": call.message.text,
            "message_link": message_link,
            "user_id": chat_id
        }
        
        print(f"🔧 Сохранены данные для {original_message_id}, user_id={chat_id}")
        
        msg = bot.send_message(
            chat_id,
            "✏️ Введите username автора в формате:\n"
            "`@username`\n\n"
            "Или отправьте ссылку на профиль:\n"
            "`https://t.me/username`",
            parse_mode='Markdown'
        )
        
        pending_contacts[original_message_id]["request_msg_id"] = msg.message_id
        bot.answer_callback_query(call.id, "Введите username автора")
        return

    if data.startswith("pub_approve_special_"):
        original_message_id = int(data.replace("pub_approve_special_", ""))
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = [types.InlineKeyboardButton(name, callback_data=f"sendto_special_{name}_{original_message_id}") for name in CHANNELS_CONFIG.keys()]
        markup.add(*buttons, types.InlineKeyboardButton("❌ Отмена", callback_data="pub_decline_special"))
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("pub_decline_special_"):
        bot.edit_message_text(f"❌ <b>ОТКЛОНЕНО</b>", chat_id, call.message.message_id, parse_mode='HTML')
        bot.answer_callback_query(call.id)
        return

    if data.startswith("sendto_special_"):
        parts = data.split("_")
        category = parts[2]
        original_message_id = int(parts[3])
        
        config = CHANNELS_CONFIG.get(category)
        if config:
            target = config["channel"]
            tags = config["tags"]
            orig = call.message.text or call.message.caption or ""
            clean = re.sub(r'#\w+(\s+#\w+)*\s*$', '', orig).strip()
            instr = "<b><code>Для публикации вакансии\\резюме, напишите заявку в </code><a href='https://t.me/Vakansii_GetJob_bot'>бота</a></b>"
            final = f"{clean.split('Для публикации вакансии')[0].strip()}\n\n{instr}{tags}"
            try:
                if call.message.content_type in ['photo', 'video', 'animation']:
                    bot.copy_message(target, chat_id, call.message.message_id, caption=final, parse_mode='HTML')
                else:
                    bot.send_message(target, final, parse_mode='HTML', disable_web_page_preview=True)
                bot.edit_message_text(f"🚀 <b>ОПУБЛИКОВАНО В: {category}</b>\n\n{final}", chat_id, call.message.message_id, parse_mode='HTML')
            except Exception as e: 
                bot.answer_callback_query(call.id, f"Ошибка: {e}")
        return

    if data.startswith("pub_"):
        action = data.replace("pub_", "")
        if action == "approve":
            markup = types.InlineKeyboardMarkup(row_width=2)
            buttons = [types.InlineKeyboardButton(name, callback_data=f"sendto_{name}") for name in CHANNELS_CONFIG.keys()]
            markup.add(*buttons, types.InlineKeyboardButton("❌ Отмена", callback_data="pub_decline"))
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
        else:
            bot.edit_message_text(f"❌ <b>ОТКЛОНЕНО</b>", chat_id, call.message.message_id, parse_mode='HTML')
        return

    if data.startswith("sendto_"):
        category = data.replace("sendto_", "")
        config = CHANNELS_CONFIG.get(category)
        if config:
            target = config["channel"]
            tags = config["tags"]
            orig = call.message.text or call.message.caption or ""
            clean = re.sub(r'#\w+(\s+#\w+)*\s*$', '', orig).strip()
            instr = "<b><code>Для публикации вакансии\\резюме, напишите заявку в </code><a href='https://t.me/Vakansii_GetJob_bot'>бота</a></b>"
            final = f"{clean.split('Для публикации вакансии')[0].strip()}\n\n{instr}{tags}"
            try:
                if call.message.content_type in ['photo', 'video', 'animation']:
                    bot.copy_message(target, chat_id, call.message.message_id, caption=final, parse_mode='HTML')
                else:
                    bot.send_message(target, final, parse_mode='HTML', disable_web_page_preview=True)
                bot.edit_message_text(f"🚀 <b>ОПУБЛИКОВАНО В: {category}</b>\n\n{final}", chat_id, call.message.message_id, parse_mode='HTML')
            except Exception as e: bot.answer_callback_query(call.id, f"Ошибка: {e}")
        return

    if data.startswith("mod_"):
        parts = data.split("_")
        action, target_id = parts[1], parts[2]
        if action == "approve":
            bot.edit_message_text(f"✅ <b>Оплата подтверждена.</b>", chat_id, call.message.message_id, parse_mode='HTML')
            bot.send_message(target_id, "✅ <b>Ваша оплата подтверждена!</b>", parse_mode='HTML')
        else:
            bot.edit_message_text(f"❌ <b>Оплата отклонена.</b>", chat_id, call.message.message_id, parse_mode='HTML')
            bot.send_message(target_id, "❌ <b>Оплата не подтверждена.</b>", parse_mode='HTML')
        return

    if data == "adm_parser":
        bot.edit_message_text("📡 Управление парсером", chat_id, call.message.message_id, reply_markup=get_parser_menu())
    elif data == "admin_panel":
        bot.edit_message_text("⚙️ Админка:", chat_id, call.message.message_id, reply_markup=get_admin_panel_markup())
    elif data == "adm_texts":
        bot.edit_message_text("📝 Тексты:", chat_id, call.message.message_id, reply_markup=get_admin_texts_markup())
    elif data == "adm_ads":
        bot.edit_message_text("📢 Управление рекламными плашками:", chat_id, call.message.message_id, reply_markup=get_admin_ad_markup())
    elif data == "adm_prices":
        bot.edit_message_text("💰 Цены:", chat_id, call.message.message_id, reply_markup=get_admin_prices_markup())
    elif data == "adm_pay":
        bot.edit_message_text("💳 Реквизиты:", chat_id, call.message.message_id, reply_markup=get_admin_pay_markup())
    
    elif data == "toggle_ad_button":
        current_settings["ad_button_enabled"] = not current_settings.get("ad_button_enabled", True)
        save_json(SETTINGS_FILE, current_settings)
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_admin_ad_markup())

    elif data.startswith("edit_"):
        key = data.replace("edit_", "")
        current_val = current_settings.get(key, "Не установлено")
        user_threads[chat_id]["state"] = "editing_setting"
        save_json(DATA_FILE, user_threads)
        msg_text = f"✍️ <b>Введите новое значение для {key}</b>\n\nТекущий текст:\n<pre>{current_val}</pre>"
        msg = safe_send_message(chat_id, msg_text, reply_markup=get_cancel_menu())
        bot.register_next_step_handler(msg, save_new_setting, key)

    elif data == "main_menu":
        user_threads[chat_id].update({"state": None, "type": "chat", "tariff": None, "notified": False})
        save_json(DATA_FILE, user_threads)
        bot.send_message(chat_id, current_settings.get("txt_start", "🏠 Меню:"), reply_markup=get_main_menu(), parse_mode='HTML')

    elif data == "back_to_text":
        utype = user_threads[chat_id].get("type", "vacancy")
        user_threads[chat_id].update({"state": "writing_text"})
        save_json(DATA_FILE, user_threads)
        txt = current_settings.get(f"txt_{utype}_instr")
        bot.send_message(chat_id, txt, reply_markup=get_nav_menu("main_menu"), parse_mode='HTML')

    elif data == "back_to_tariff":
        user_threads[chat_id].update({"state": "waiting_tariff"})
        save_json(DATA_FILE, user_threads)
        bot.send_message(chat_id, "💎 Выберите тип размещения:", reply_markup=get_tariff_menu())

    elif data == "back_to_payment_choice":
        user_threads[chat_id].update({"state": "waiting_payment_choice"})
        save_json(DATA_FILE, user_threads)
        bot.send_message(chat_id, "✅ Выберите способ оплаты:", reply_markup=get_payment_choice_menu())

    elif data.startswith("parser_"):
        table = data.replace("parser_", "")
        if table == "special_chats":
            display_table = "special_chats"
        else:
            display_table = table
        bot.edit_message_text(f"Управление: {table}", chat_id, call.message.message_id, reply_markup=get_db_manage_markup(display_table))

    elif data.startswith("add_"):
        table = data.replace("add_", "")
        user_threads[chat_id]["state"] = f"adding_{table}"
        save_json(DATA_FILE, user_threads)
        
        if table == "special_chats":
            hint = "\n\nВведите ID чата (например: -1001234567890)"
        else:
            hint = ""
        
        msg = bot.send_message(chat_id, f"Введите значение:{hint}", reply_markup=get_cancel_parser_menu())
        bot.register_next_step_handler(msg, process_db_add, table)

    elif data.startswith("del_"):
        p = data.split("_")
        table_name = "_".join(p[1:-1])
        item_id = p[-1]
        delete_db_item(table_name, item_id)
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_db_manage_markup(table_name))

    elif data.startswith("set_tariff_"):
        user_threads[chat_id].update({"tariff": data.replace("set_tariff_", ""), "state": "waiting_payment_choice"})
        save_json(DATA_FILE, user_threads)
        bot.edit_message_text("✅ Выберите способ оплаты:", chat_id, call.message.message_id, reply_markup=get_payment_choice_menu())

    elif data in ["pay_rf", "pay_rb", "pay_crypto"]:
        pay_info = current_settings.get(data, "")
        wait_check_text = current_settings.get("txt_wait_check", "\n\nПришлите чек:")
        final_text = f"{pay_info}\n\n{wait_check_text}"
        bot.delete_message(chat_id, call.message.message_id) 
        msg = safe_send_message(chat_id, final_text, reply_markup=get_nav_menu("back_to_payment_choice"))
        user_threads[chat_id]["state"] = "waiting_screenshot"
        save_json(DATA_FILE, user_threads)
        bot.register_next_step_handler(msg, wait_for_screenshot, user_threads[chat_id])

    elif data == "toggle_logging":
        current_settings["logging_enabled"] = not current_settings.get("logging_enabled", True)
        save_json(SETTINGS_FILE, current_settings)
        bot.edit_message_text("⚙️ Админка:", chat_id, call.message.message_id, reply_markup=get_admin_panel_markup())

    elif data in ["vacancy", "resume", "admin_chat"]:
        user_threads[chat_id].update({"type": data, "state": "writing_text", "notified": False})
        save_json(DATA_FILE, user_threads)
        txt = current_settings.get(f"txt_{data}_instr" if data != "admin_chat" else "txt_admin_chat")
        bot.edit_message_text(txt, chat_id, call.message.message_id, reply_markup=get_nav_menu("main_menu"), parse_mode='HTML')

    elif data == "ad":
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✉️ Админ", url="https://t.me/dzmitrynero"), types.InlineKeyboardButton("🏠 Меню", callback_data="main_menu"))
        bot.edit_message_text(current_settings.get("txt_ad_info"), chat_id, call.message.message_id, reply_markup=markup, parse_mode='HTML')

    bot.answer_callback_query(call.id)

# Обработка текстовых сообщений от админа
@bot.message_handler(func=lambda m: (str(m.chat.id) == str(ADMIN_ID) or m.from_user.id == ADMIN_ID) and pending_contacts)
def handle_admin_text(message):
    chat_id = str(message.chat.id)
    
    print(f"🔧 handle_admin_text вызван, текст: {message.text}")
    print(f"🔧 pending_contacts: {pending_contacts}")
    
    for original_msg_id, data in list(pending_contacts.items()):
        print(f"🔧 Проверяем original_msg_id={original_msg_id}, user_id={data.get('user_id')}, chat_id={chat_id}")
        if data.get("user_id") == chat_id:
            print(f"🔧 Найдено ожидание для {original_msg_id}")
            
            contact_input = message.text.strip()
            print(f"🔧 contact_input: {contact_input}")
            
            if contact_input.startswith('@'):
                username = contact_input[1:]
            elif 't.me/' in contact_input:
                username = contact_input.split('t.me/')[-1]
            else:
                username = contact_input
            
            formatted_contact = f"@{username}"
            print(f"🔧 formatted_contact: {formatted_contact}")
            
            original_text = data["original_text"]
            
            contact_marker = "Контакт для связи:"
            next_marker = "Для публикации вакансии"
            
            contact_pos = original_text.find(contact_marker)
            next_pos = original_text.find(next_marker, contact_pos)
            
            if contact_pos != -1 and next_pos != -1:
                after_marker = contact_pos + len(contact_marker)
                before = original_text[:after_marker]
                after = original_text[next_pos:]
                updated_text = f"{before}\n{formatted_contact}\n\n{after}"
                print(f"🔧 Текст обновлён (чистая замена)")
            else:
                updated_text = original_text.replace(
                    "<i>⚠️ Контакт не найден (укажите @username или добавьте контакт в текст)</i>",
                    formatted_contact
                )
                print(f"🔧 Текст обновлён через замену")
            
            print(f"🔧 Пытаемся обновить сообщение {original_msg_id} в группе {SUPER_GROUP_ID}")
            
            try:
                bot.edit_message_text(
                    updated_text,
                    SUPER_GROUP_ID,
                    original_msg_id,
                    parse_mode='HTML',
                    reply_markup=get_special_moderation_after_edit_markup(original_msg_id, data.get("message_link"))
                )
                print(f"✅ Сообщение {original_msg_id} успешно обновлено!")
                bot.send_message(chat_id, f"✅ Контакт {formatted_contact} добавлен!")
                
                try:
                    bot.delete_message(chat_id, data.get("request_msg_id"))
                    print(f"✅ Сообщение с запросом удалено")
                except Exception as e:
                    print(f"⚠️ Не удалось удалить сообщение запроса: {e}")
                
                del pending_contacts[original_msg_id]
                print(f"✅ pending_contacts очищен для {original_msg_id}")
                
            except Exception as e:
                error_msg = str(e)
                print(f"❌ Ошибка при обновлении: {error_msg}")
                bot.send_message(chat_id, f"❌ Ошибка: {error_msg}")
            
            return
    
    print("🔧 Нет ожидающих контактов для этого пользователя")

# Обработчики для шагов добавления
def save_recommend_button_text(message):
    chat_id = str(message.chat.id)
    if message.text and not message.text.startswith('/'):
        update_recommend_settings(button_text=message.text)
        bot.send_message(chat_id, "✅ Текст кнопки обновлён!", reply_markup=get_nav_menu("adm_recommends"))
    user_threads = load_json(DATA_FILE, {})
    if chat_id in user_threads:
        user_threads[chat_id]["state"] = None
        save_json(DATA_FILE, user_threads)

def save_select_category_text(message):
    chat_id = str(message.chat.id)
    if message.text and not message.text.startswith('/'):
        update_recommend_settings(select_category_text=message.text)
        bot.send_message(chat_id, "✅ Текст 'Выберите категорию' обновлён!", reply_markup=get_nav_menu("adm_recommends"))
    user_threads = load_json(DATA_FILE, {})
    if chat_id in user_threads:
        user_threads[chat_id]["state"] = None
        save_json(DATA_FILE, user_threads)

def save_select_specialist_text(message):
    chat_id = str(message.chat.id)
    if message.text and not message.text.startswith('/'):
        update_recommend_settings(select_specialist_text=message.text)
        bot.send_message(chat_id, "✅ Текст 'Выберите специалиста' обновлён!", reply_markup=get_nav_menu("adm_recommends"))
    user_threads = load_json(DATA_FILE, {})
    if chat_id in user_threads:
        user_threads[chat_id]["state"] = None
        save_json(DATA_FILE, user_threads)

def add_category_step(message):
    chat_id = str(message.chat.id)
    if message.text and not message.text.startswith('/'):
        text = message.text.strip()
        icon = text[0] if text[0] in "🎥📱💻✍️📊🎨⭐📁" else "📁"
        name = text if icon == "📁" else text[1:].strip()
        add_category(name, icon)
        bot.send_message(chat_id, f"✅ Категория {icon} {name} добавлена!", reply_markup=get_nav_menu("manage_categories"))
    user_threads = load_json(DATA_FILE, {})
    if chat_id in user_threads:
        user_threads[chat_id]["state"] = None
        save_json(DATA_FILE, user_threads)

def add_card_text_step(message):
    chat_id = str(message.chat.id)
    user_threads = load_json(DATA_FILE, {})
    if message.text and not message.text.startswith('/'):
        custom_text = message.text.strip()
        cat_id = user_threads.get(chat_id, {}).get("temp_category")
        if cat_id:
            user_threads[chat_id]["temp_custom_text"] = custom_text
            save_json(DATA_FILE, user_threads)
            msg = bot.send_message(chat_id, "📸 Теперь отправьте фото для карточки (или нажмите /skip чтобы пропустить):", reply_markup=get_cancel_menu())
            bot.register_next_step_handler(msg, add_card_photo_step)
        else:
            bot.send_message(chat_id, "❌ Ошибка: категория не найдена")
    else:
        if chat_id in user_threads:
            user_threads[chat_id]["state"] = None
            user_threads[chat_id].pop("temp_category", None)
            save_json(DATA_FILE, user_threads)

def add_card_photo_step(message):
    chat_id = str(message.chat.id)
    user_threads = load_json(DATA_FILE, {})
    
    photo_file_id = None
    if message.text and message.text == '/skip':
        photo_file_id = None
    elif message.content_type == 'photo':
        photo_file_id = message.photo[-1].file_id
    else:
        msg = bot.send_message(chat_id, "❌ Пожалуйста, отправьте фото (или нажмите /skip чтобы пропустить):", reply_markup=get_cancel_menu())
        bot.register_next_step_handler(msg, add_card_photo_step)
        return
    
    custom_text = user_threads.get(chat_id, {}).get("temp_custom_text")
    cat_id = user_threads.get(chat_id, {}).get("temp_category")
    
    if cat_id and custom_text:
        msg = bot.send_message(chat_id, "✍️ Теперь введите контакт специалиста (username или ссылка):\n\nПример: @username", reply_markup=get_cancel_menu())
        bot.register_next_step_handler(msg, add_card_contact_step, photo_file_id)
    else:
        bot.send_message(chat_id, "❌ Ошибка: не хватает данных")

def add_card_contact_step(message, photo_file_id):
    chat_id = str(message.chat.id)
    user_threads = load_json(DATA_FILE, {})
    if message.text and not message.text.startswith('/'):
        contact = message.text.strip()
        custom_text = user_threads.get(chat_id, {}).get("temp_custom_text")
        cat_id = user_threads.get(chat_id, {}).get("temp_category")
        if cat_id and custom_text:
            add_card(cat_id, custom_text, contact, photo_file_id)
            bot.send_message(chat_id, "✅ Карточка добавлена!", reply_markup=get_nav_menu("manage_cards"))
        else:
            bot.send_message(chat_id, "❌ Ошибка: не хватает данных")
    if chat_id in user_threads:
        user_threads[chat_id]["state"] = None
        user_threads[chat_id].pop("temp_category", None)
        user_threads[chat_id].pop("temp_custom_text", None)
        save_json(DATA_FILE, user_threads)

# ==================== HANDLERS ====================

@bot.message_handler(commands=['start', 'admin_panel', 'recommends', 'topss'])
def commands_handler(message):
    chat_id = str(message.chat.id)
    bot.clear_step_handler_by_chat_id(chat_id)
    user_threads = load_json(DATA_FILE, {})
    
    if message.text in ['/recommends', '/topss']:
        categories = get_categories()
        settings = get_recommend_settings()
        if not categories:
            bot.send_message(chat_id, "📭 Пока нет доступных категорий.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for cat in categories:
            count = len(get_cards_by_category(cat["id"]))
            markup.add(types.InlineKeyboardButton(f"{cat['icon']} {cat['name']} ({count})", callback_data=f"cat_{cat['id']}"))
        markup.add(types.InlineKeyboardButton("🏠 В меню", callback_data="main_menu"))
        bot.send_message(chat_id, settings["select_category_text"], reply_markup=markup, parse_mode='HTML')
        return
    
    if chat_id not in user_threads or not user_threads[chat_id].get("thread_id"):
        try:
            user_name = message.from_user.first_name or "User"
            topic = bot.create_forum_topic(SUPER_GROUP_ID, f"{user_name} ({chat_id})")
            user_threads[chat_id] = {
                "thread_id": topic.message_thread_id, 
                "type": "chat", 
                "state": None, 
                "notified": False,
                "msg_count": 0
            }
            save_json(DATA_FILE, user_threads)
            
            username_tg = f"@{message.from_user.username}" if message.from_user.username else "нет"
            admin_msg = f"🆕 <b>Новый пользователь зашел в бота!</b>\n\nИмя: {user_name}\nTG: {username_tg}\nID: <code>{chat_id}</code>"
            bot.send_message(SUPER_GROUP_ID, admin_msg, message_thread_id=topic.message_thread_id, parse_mode='HTML')
        except Exception as e:
            if chat_id not in user_threads: user_threads[chat_id] = {"thread_id": None}
    
    user_threads[chat_id].update({"type": "chat", "state": None, "notified": False})
    save_json(DATA_FILE, user_threads)
    
    if message.text in ['/admin_panel', '/start'] and message.from_user.id == ADMIN_ID:
        bot.send_message(chat_id, "⚙️ Панель администратора:", reply_markup=get_admin_panel_markup())
    elif message.text == '/start':
        bot.send_message(chat_id, current_settings.get("txt_start"), 
                         reply_markup=get_reply_main_menu(), parse_mode='HTML')
        bot.send_message(chat_id, "Выберите действие:", reply_markup=get_main_menu())
    else:
        bot.send_message(chat_id, current_settings.get("txt_start"), 
                         reply_markup=get_reply_main_menu(), parse_mode='HTML')
        bot.send_message(chat_id, "Выберите действие:", reply_markup=get_main_menu())

@bot.message_handler(func=lambda m: m.chat.id == SUPER_GROUP_ID and m.reply_to_message is not None)
def handle_admin_reply(message):
    user_threads = load_json(DATA_FILE, {})
    target_id = next((u for u, d in user_threads.items() if d.get("thread_id") == message.message_thread_id), None)
    if target_id:
        try: bot.copy_message(target_id, message.chat.id, message.message_id)
        except: pass

@bot.message_handler(func=lambda m: m.chat.type == 'private', content_types=['text', 'photo', 'video', 'document', 'animation'])
def handle_user_messages(message):
    chat_id = str(message.chat.id)
    
    if (str(chat_id) == str(ADMIN_ID) or message.from_user.id == ADMIN_ID) and pending_contacts:
        for original_msg_id, data in pending_contacts.items():
            if data.get("user_id") == chat_id:
                handle_admin_text(message)
                return
    
    if message.text == "🏠 Главное меню":
        bot.clear_step_handler_by_chat_id(chat_id)
        user_threads = load_json(DATA_FILE, {})
        if chat_id in user_threads:
            user_threads[chat_id].update({"state": None, "type": "chat", "tariff": None, "notified": False})
            save_json(DATA_FILE, user_threads)
        
        bot.send_message(chat_id, "🔄 Возвращаемся в главное меню.", reply_markup=get_reply_main_menu())
        bot.send_message(chat_id, current_settings.get("txt_start", "🏠 Меню:"), reply_markup=get_main_menu(), parse_mode='HTML')
        return

    if message.text and message.text.startswith('/'): return
    
    user_threads = load_json(DATA_FILE, {})
    if chat_id not in user_threads: 
        user_threads[chat_id] = {"thread_id": None, "type": "chat", "state": None, "notified": False}
    
    user_data = user_threads[chat_id]

    if user_data.get("state") in ["waiting_tariff", "waiting_payment_choice"] and user_data.get("type") in ["vacancy", "resume"]:
        bot.send_message(chat_id, "⚠️ Используйте кнопки меню для навигации.")
        return

    if not user_data.get("thread_id"):
        try:
            topic = bot.create_forum_topic(SUPER_GROUP_ID, f"{message.from_user.first_name}")
            user_data["thread_id"] = topic.message_thread_id
            save_json(DATA_FILE, user_threads)
        except: return

    if user_data.get("type") in ["vacancy", "resume"] and user_data.get("state") == "writing_text":
        label = "💼 <b>ВАКАНСИЯ</b>" if user_data["type"] == "vacancy" else "👤 <b>РЕЗЮМЕ</b>"
        bot.send_message(SUPER_GROUP_ID, label, message_thread_id=user_data["thread_id"], parse_mode='HTML')
        bot.copy_message(SUPER_GROUP_ID, chat_id, message.message_id, message_thread_id=user_data["thread_id"], reply_markup=get_user_info_btn(chat_id))
        
        user_threads[chat_id]["state"] = "writing_time"
        save_json(DATA_FILE, user_threads)
        
        wait_time_text = current_settings.get("txt_wait_time", "Напишите время публикации:")
        msg = safe_send_message(chat_id, wait_time_text, reply_markup=get_nav_menu("back_to_text"))
        bot.register_next_step_handler(msg, process_submission_time, user_threads[chat_id])
    else:
        bot.copy_message(SUPER_GROUP_ID, chat_id, message.message_id, message_thread_id=user_data["thread_id"], reply_markup=get_user_info_btn(chat_id))
        if not user_data.get("notified"):
            bot.send_message(chat_id, "✅ Сообщение отправлено.")
            user_threads[chat_id]["notified"] = True
            save_json(DATA_FILE, user_threads)

    check_and_send_ad(chat_id)

if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling(skip_pending=True)