import telebot
from telebot import types
import json
import os
import sqlite3
import re

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

# --- РАБОТА С БАЗОЙ ДАННЫХ ПАРСЕРА ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY, url TEXT UNIQUE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS keywords (id INTEGER PRIMARY KEY, word TEXT UNIQUE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS stop_words (id INTEGER PRIMARY KEY, word TEXT UNIQUE)')
    conn.commit()
    conn.close()

init_db()

def get_db_items(table):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    col = "url" if table == "channels" else "word"
    cursor.execute(f'SELECT id, {col} FROM {table}')
    items = cursor.fetchall()
    conn.close()
    return items

def add_db_item(table, value):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        col = "url" if table == "channels" else "word"
        cursor.execute(f'INSERT INTO {table} ({col}) VALUES (?)', (value,))
        conn.commit()
        conn.close()
        return True
    except: return False

def delete_db_item(table, item_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f'DELETE FROM {table} WHERE id = ?', (item_id,))
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
    markup.add(
        types.InlineKeyboardButton("📋 Опубликовать вакансию", callback_data="vacancy"),
        types.InlineKeyboardButton("👤 Опубликовать резюме", callback_data="resume"),
        types.InlineKeyboardButton("📢 Опубликовать рекламу", callback_data="ad"),
        types.InlineKeyboardButton("✉️ Связаться с модератором", callback_data="admin_chat")
    )
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
        types.InlineKeyboardButton("🔑 КЛЮЧЕВЫЕ СЛОВА", callback_data="parser_words"),
        types.InlineKeyboardButton("🚫 СТОП-СЛОВА", callback_data="parser_stop_words"),
        types.InlineKeyboardButton("🔙 Назад в админку", callback_data="admin_panel")
    )
    return markup

def get_db_manage_markup(table):
    markup = types.InlineKeyboardMarkup(row_width=1)
    items = get_db_items(table)
    for item_id, val in items:
        markup.add(types.InlineKeyboardButton(f"❌ Удалить: {val}", callback_data=f"del_{table}_{item_id}"))
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

# ==================== ЛОГИКА ШАГОВ (STEPS) ====================

def process_db_add(message, table):
    chat_id = str(message.chat.id)
    if message.text and message.text.startswith('/'): return
    
    if add_db_item(table, message.text):
        bot.send_message(chat_id, "✅ Успешно добавлено в базу!")
    else:
        bot.send_message(chat_id, "❌ Ошибка при добавлении.")
    
    user_threads = load_json(DATA_FILE, {})
    user_threads[chat_id]["state"] = None
    save_json(DATA_FILE, user_threads)
    bot.send_message(chat_id, "📡 Меню управления парсером:", reply_markup=get_parser_menu())

def save_new_setting(message, key):
    chat_id = str(message.chat.id)
    user_threads = load_json(DATA_FILE, {})
    if user_threads.get(chat_id, {}).get("state") != "editing_setting" or message.text == '/start':
        return
    current_settings[key] = message.text
    save_json(SETTINGS_FILE, current_settings)
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
    if user_threads.get(chat_id, {}).get("state") != "writing_time":
        return

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
    
    user_threads[chat_id].update({"state": None, "type": "chat", "tariff": None})
    save_json(DATA_FILE, user_threads)

# ==================== ОБРАБОТЧИК CALLBACK ====================

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = str(call.message.chat.id)
    data = call.data
    
    bot.clear_step_handler_by_chat_id(chat_id)
    
    user_threads = load_json(DATA_FILE, {})
    if chat_id not in user_threads: user_threads[chat_id] = {}

    if data.startswith("user_info_"):
        u_id = data.replace("user_info_", "")
        try:
            u_chat = bot.get_chat(u_id)
            info = (f"👤 <b>ИНФО:</b>\n🆔 ID: <code>{u_id}</code>\n📛: {u_chat.first_name}\n🏷: @{u_chat.username}\n📝: {u_chat.bio}\n🔗 <a href='tg://user?id={u_id}'>Профиль</a>")
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, info, message_thread_id=call.message.message_thread_id, parse_mode='HTML')
        except: bot.answer_callback_query(call.id, "Ошибка получения данных", show_alert=True)
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
        bot.edit_message_text(current_settings.get("txt_start", "🏠 Меню:"), chat_id, call.message.message_id, reply_markup=get_main_menu(), parse_mode='HTML')

    elif data == "back_to_text":
        utype = user_threads[chat_id].get("type", "vacancy")
        user_threads[chat_id].update({"state": "writing_text"})
        save_json(DATA_FILE, user_threads)
        txt = current_settings.get(f"txt_{utype}_instr")
        bot.edit_message_text(txt, chat_id, call.message.message_id, reply_markup=get_nav_menu("main_menu"), parse_mode='HTML')

    elif data == "back_to_tariff":
        user_threads[chat_id].update({"state": "waiting_tariff"})
        save_json(DATA_FILE, user_threads)
        bot.edit_message_text("💎 Выберите тип размещения:", chat_id, call.message.message_id, reply_markup=get_tariff_menu())

    elif data == "back_to_payment_choice":
        user_threads[chat_id].update({"state": "waiting_payment_choice"})
        save_json(DATA_FILE, user_threads)
        bot.edit_message_text("✅ Выберите способ оплаты:", chat_id, call.message.message_id, reply_markup=get_payment_choice_menu())

    elif data.startswith("parser_"):
        table = data.replace("parser_", "")
        bot.edit_message_text(f"Управление: {table}", chat_id, call.message.message_id, reply_markup=get_db_manage_markup(table))

    elif data.startswith("add_"):
        table = data.replace("add_", "")
        user_threads[chat_id]["state"] = f"adding_{table}"
        save_json(DATA_FILE, user_threads)
        msg = bot.send_message(chat_id, "Введите значение:", reply_markup=get_cancel_parser_menu())
        bot.register_next_step_handler(msg, process_db_add, table)

    elif data.startswith("del_"):
        p = data.split("_")
        delete_db_item("_".join(p[1:-1]), p[-1])
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_db_manage_markup("_".join(p[1:-1])))

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

# ==================== HANDLERS ====================

@bot.message_handler(commands=['start', 'admin_panel'])
def commands_handler(message):
    chat_id = str(message.chat.id)
    bot.clear_step_handler_by_chat_id(chat_id)
    user_threads = load_json(DATA_FILE, {})
    
    # --- НОВАЯ ФИШКА: Создание топика сразу при /start ---
    if chat_id not in user_threads or not user_threads[chat_id].get("thread_id"):
        try:
            user_name = message.from_user.first_name or "User"
            # Создаем топик
            topic = bot.create_forum_topic(SUPER_GROUP_ID, f"{user_name} ({chat_id})")
            
            # Инициализируем данные
            user_threads[chat_id] = {
                "thread_id": topic.message_thread_id, 
                "type": "chat", 
                "state": None, 
                "notified": False,
                "msg_count": 0
            }
            save_json(DATA_FILE, user_threads)
            
            # Уведомление для админа в новый топик
            username_tg = f"@{message.from_user.username}" if message.from_user.username else "нет"
            admin_msg = f"🆕 <b>Новый пользователь зашел в бота!</b>\n\nИмя: {user_name}\nTG: {username_tg}\nID: <code>{chat_id}</code>"
            bot.send_message(SUPER_GROUP_ID, admin_msg, message_thread_id=topic.message_thread_id, parse_mode='HTML')
            print(f"✅ Создан топик для {user_name}")
        except Exception as e:
            print(f"❌ Ошибка создания топика: {e}")
            if chat_id not in user_threads: user_threads[chat_id] = {"thread_id": None}
    
    user_threads[chat_id].update({"type": "chat", "state": None, "notified": False})
    save_json(DATA_FILE, user_threads)
    
    if message.text == '/admin_panel' and message.from_user.id == ADMIN_ID:
        bot.send_message(chat_id, "⚙️ Панель администратора:", reply_markup=get_admin_panel_markup())
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
        # Если вдруг юзер пишет, а топика нет (напр. бот был выключен при /start)
        user_threads[chat_id] = {"thread_id": None, "type": "chat", "state": None, "notified": False}
    
    user_data = user_threads[chat_id]

    if user_data.get("state") in ["waiting_tariff", "waiting_payment_choice"] and user_data.get("type") in ["vacancy", "resume"]:
        bot.send_message(chat_id, "⚠️ Используйте кнопки меню для навигации.")
        return

    # Запасная проверка топика перед отправкой
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