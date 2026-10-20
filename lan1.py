from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=10000)
import os
import telebot
from telebot import types
import sqlite3
from google import genai
from google.genai import types as genai_types
from datetime import datetime, timedelta

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", ))
ADMIN_USERNAME = "@Suyeta97"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", " ")

PAYMENT_REQUISITES = """
💳 **Реквизиты для оплаты подписки:**

Карта / : `05 317 9797`
Банк: душанбе сити, эсхата
Сумма: 10 сомони / месяц

После оплаты отправьте **скриншот чека** прямо в этот чат!
"""
# ============================================

bot = telebot.TeleBot(BOT_TOKEN)
ai_client = genai.Client(api_key=GEMINI_API_KEY)
user_profiles = {}

def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_vip INTEGER DEFAULT 0,
            state TEXT,
            gender TEXT,
            want_girl TEXT,
            topic TEXT,
            native_lang TEXT,
            target_lang TEXT,
            sub_end_date TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user(user_id, **kwargs):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    for key, value in kwargs.items():
        cursor.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

# ----------------- НОВОЕ: КНОПКА МЕНЮ -----------------
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_restart = types.KeyboardButton("🔄 Начать заново")
    btn_help = types.KeyboardButton("🆘 Связь с админом")
    markup.add(btn_restart, btn_help)
    return markup

# ----------------- СТАРТ И ПЕРЕЗАПУСК -----------------
@bot.message_handler(commands=['start', 'restart'])
@bot.message_handler(func=lambda msg: msg.text == "🔄 Начать заново")
def start_cmd(message):
    user_id = message.chat.id
    
    # Сбрасываем старые настройки в базе данных
    conn = sqlite3.connect("bot_database.db")
    conn.execute("""
        INSERT OR REPLACE INTO users 
        (user_id, is_vip, state, gender, want_girl, topic, native_lang, target_lang, sub_end_date) 
        VALUES (?, 0, 'set_gender', NULL, NULL, NULL, NULL, NULL, NULL)
    """, (user_id,))
    conn.commit()
    conn.close()

    user_profiles[user_id] = {} 

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Мужчина", "Женщина")
    
    bot.send_message(
        user_id, 
        "Привет! 👋 Я твой ИИ-собеседник.\n\nДавай настроим профиль заново. Скажи, **кто ты?**", 
        reply_markup=markup, 
        parse_mode="Markdown"
    )

# ----------------- СВЯЗЬ С АДМИНОМ -----------------
@bot.message_handler(commands=['help', 'admin'])
@bot.message_handler(func=lambda msg: msg.text == "🆘 Связь с админом")
def help_command(message):
    bot.send_message(
        message.chat.id,
        f"Если у тебя возникли проблемы с ботом, оплатой или ИИ ведет себя странно — напиши напрямую администратору:\n\n👉 @{ADMIN_USERNAME}\n\n(Или напиши сюда, и я перешлю сообщение админу)",
        reply_markup=get_main_menu()
    )

# Пересылка любого текста админу, если пользователь нажал "Связь с админом" (опционально)
@bot.message_handler(func=lambda msg: msg.text and "напиши напрямую" in msg.text)
def forward_to_admin(message):
    # Этот обработчик можно расширить, если нужно пересылать сообщения
    pass

# ----------------- АНКЕТА -----------------
@bot.message_handler(func=lambda msg: msg.text in ["Мужчина", "Женщина"] and get_user(msg.chat.id) and get_user(msg.chat.id)[2] == 'set_gender')
def set_gender(message):
    user_id = message.chat.id
    user_profiles[user_id]['gender'] = message.text
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Да", "Нет")
    bot.send_message(user_id, "Хочешь общаться со мной как с девушкой? 😉", reply_markup=markup)
    update_user(user_id, state='set_want_girl', gender=message.text)

@bot.message_handler(func=lambda msg: msg.text in ["Да", "Нет"] and get_user(msg.chat.id) and get_user(msg.chat.id)[2] == 'set_want_girl')
def set_want_girl(message):
    user_id = message.chat.id
    user_profiles[user_id]['want_girl'] = message.text
    
    bot.send_message(user_id, "Отлично! Какая **тема общения** тебе интересна? (Напиши текстом)", reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")
    update_user(user_id, state='set_topic', want_girl=message.text)

@bot.message_handler(func=lambda msg: get_user(msg.chat.id) and get_user(msg.chat.id)[2] == 'set_topic')
def set_topic(message):
    user_id = message.chat.id
    user_profiles[user_id]['topic'] = message.text
    
    bot.send_message(
        user_id, 
        "Настройка профиля завершена! ✅\n\nЧтобы начать общение, нужна подписка.\n\n" + PAYMENT_REQUISITES,
        reply_markup=get_main_menu(), # Добавили меню сюда тоже
        parse_mode="Markdown"
    )
    update_user(user_id, state='wait_payment', topic=message.text)

# ----------------- ОПЛАТА -----------------
@bot.message_handler(content_types=['photo'])
def handle_payment_screenshot(message):
    user_id = message.chat.id
    bot.send_message(user_id, "⏳ Ваш чек отправлен на проверку администратору. Ожидайте!")
    
    markup = types.InlineKeyboardMarkup()
    btn_approve = types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{user_id}")
    btn_reject = types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}")
    markup.add(btn_approve, btn_reject)
    
    username = f"@{message.from_user.username}" if message.from_user.username else "Нет юзернейма"
    caption = f"**Новый чек!**\nЮзер: {username} (ID: `{user_id}`)"
    
    bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=caption, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'reject_')))
def admin_decision(call):
    action, user_id = call.data.split('_')
    user_id = int(user_id)
    
    if action == 'approve':
        end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        update_user(user_id, is_vip=1, state='ask_native_lang', sub_end_date=end_date)
        
        bot.send_message(user_id, f"🎉 **Ваша подписка подтверждена!**\nОна будет активна до **{end_date}**.\n\nТеперь давай настроим твое обучение.")
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add("Русский", "English", "Тоҷикӣ", "O'zbekcha")
        bot.send_message(user_id, "**На каком языке ты говоришь?**", reply_markup=markup, parse_mode="Markdown")
        
        bot.edit_message_caption("✅ Оплата **ПОДТВЕРЖДЕНА**", chat_id=call.message.chat.id, message_id=call.message.message_id)
        
    elif action == 'reject':
        update_user(user_id, state='wait_payment')
        bot.send_message(user_id, "❌ Оплата не подтверждена. Пожалуйста, проверьте чек.", reply_markup=get_main_menu())
        bot.edit_message_caption("❌ Оплата **ОТКЛОНЕНА**", chat_id=call.message.chat.id, message_id=call.message.message_id)

# ----------------- ЯЗЫКИ -----------------
@bot.message_handler(func=lambda msg: get_user(msg.chat.id) and get_user(msg.chat.id)[2] == 'ask_native_lang')
def set_native_lang(message):
    user_id = message.chat.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Английский", "Китайский", "Немецкий", "Испанский", "Французский")
    bot.send_message(user_id, "Отлично! **Какой язык ты хочешь изучать?**", reply_markup=markup, parse_mode="Markdown")
    update_user(user_id, state='ask_target_lang', native_lang=message.text)

@bot.message_handler(func=lambda msg: get_user(msg.chat.id) and get_user(msg.chat.id)[2] == 'ask_target_lang')
def set_target_lang(message):
    user_id = message.chat.id
    bot.send_message(
        user_id, 
        f"Супер! Ты будешь изучать **{message.text}**.\n\nНастройка полностью завершена! Теперь пиши мне сообщения 🚀", 
        reply_markup=get_main_menu(), # Возвращаем меню
        parse_mode="Markdown"
    )
    update_user(user_id, state='active', target_lang=message.text)

# ----------------- ОБЩЕНИЕ С ИИ -----------------
@bot.message_handler(func=lambda msg: msg.content_type == 'text' and get_user(msg.chat.id) and get_user(msg.chat.id)[2] == 'active')
def ai_chat(message):
    if message.text in ["🔄 Начать заново", "🆘 Связь с админом"]:
        return

    user_id = message.chat.id
    user = get_user(user_id)
    
    sub_end_date_str = user[8]
    if sub_end_date_str:
        sub_end_date = datetime.strptime(sub_end_date_str, "%Y-%m-%d")
        if datetime.now() > sub_end_date:
            update_user(user_id, is_vip=0, state='wait_payment')
            bot.send_message(
                user_id, 
                "😔 Ой, срок твоей подписки закончился!\n\nЧтобы продолжить, оплати 10 сомони и отправь новый чек.\n\n" + PAYMENT_REQUISITES,
                reply_markup=get_main_menu(),
                parse_mode="Markdown"
            )
            return

    gender = user[3]
    want_girl = user[4]
    topic = user[5]
    native_lang = user[6]
    target_lang = user[7]

    system_instruction = f"""
    Ты — живой, интересный собеседник и репетитор.
    Пользователь: {gender}. Родной язык: {native_lang}. Учит: {target_lang}.
    Тема: {topic}. Общение как с девушкой: {want_girl}.
    
    ПРАВИЛА:
    1. Общайся живо, с эмодзи.
    2. Если "как с девушкой" = Да, используй женский род, кокетничай.
    3. Поддерживай интригу, шути.
    4. Вставляй фразы на {target_lang} с переводом на {native_lang}.
    """

    bot.send_chat_action(message.chat.id, 'typing')
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.1-flash-lite', 
            contents=message.text,
            config=genai_types.GenerateContentConfig(system_instruction=system_instruction)
        )
        bot.reply_to(message, response.text)
    except Exception as e:
        error_text = str(e)
        if "503" in error_text or "UNAVAILABLE" in error_text:
            import time
            time.sleep(2)
            try:
                response = ai_client.models.generate_content(
                    model='gemini-3.1-flash-lite', 
                    contents=message.text,
                    config=genai_types.GenerateContentConfig(system_instruction=system_instruction)
                )
                bot.reply_to(message, response.text)
            except:
                bot.reply_to(message, "Ой, у меня на секунду зависли мысли... 🥺 Google перегружен. Попробуй написать еще раз через минутку!")
        else:
            bot.reply_to(message, f"⚠️ Ошибка: {e}")
        print(f"ОШИБКА ИИ: {e}")

if __name__ == "__main__":
    print("Бот успешно запущен!")
    threading.Thread(target=run_flask, daemon=True).start()
    bot.infinity_polling()
