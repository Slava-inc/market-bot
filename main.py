import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import os
from dotenv import load_dotenv

import logging

# Загрузка переменных окружения
load_dotenv(dotenv_path='env_var')

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('market.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name TEXT,
            price REAL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            product_id INTEGER
        )
    ''')
    conn.commit()
    # Заполним товары (91 цифровой товар)
    for i in range(1, 92):
        c.execute("INSERT OR IGNORE INTO products (id, name, price) VALUES (?, ?, ?)", (i, f"Товар {i}", 10.0))
    conn.close()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('market.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("💰 Баланс", callback_data='balance')],
        [InlineKeyboardButton("📥 Пополнить", callback_data='deposit')],
        [InlineKeyboardButton("📤 Вывести", callback_data='withdraw')],
        [InlineKeyboardButton("🛍️ Каталог товаров", callback_data='products')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Добро пожаловать в маркет!', reply_markup=reply_markup)

# Обработчик inline-кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    conn = sqlite3.connect('market.db')
    c = conn.cursor()

    if query.data == 'balance':
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        balance = c.fetchone()[0]
        await query.edit_message_text(f'Ваш баланс: {balance} руб.')

    elif query.data == 'deposit':
        await query.edit_message_text("Для пополнения переведите сумму на наш счёт.\nПосле оплаты напишите /confirm <сумма>")

    elif query.data == 'withdraw':
        await query.edit_message_text("Для вывода средств напишите /withdraw <сумма>")

    elif query.data == 'products':
        keyboard = []
        c.execute("SELECT id, name, price FROM products")
        products = c.fetchall()
        for pid, name, price in products:
            keyboard.append([InlineKeyboardButton(f"{name} - {price} руб.", callback_data=f'buy_{pid}')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите товар для покупки:", reply_markup=reply_markup)

    elif query.data.startswith('buy_'):
        product_id = int(query.data.split('_')[1])
        c.execute("SELECT price FROM products WHERE id = ?", (product_id,))
        price = c.fetchone()[0]
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        balance = c.fetchone()[0]

        if balance >= price:
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, user_id))
            c.execute("INSERT INTO transactions (user_id, type, amount, product_id) VALUES (?, ?, ?, ?)",
                      (user_id, 'purchase', -price, product_id))
            conn.commit()
            await query.edit_message_text(f"✅ Куплен товар {product_id}.")
        else:
            await query.edit_message_text("❌ Недостаточно средств.")

    conn.close()

# Команда для пополнения (после оплаты)
async def confirm_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(context.args[0])
        user_id = update.effective_user.id
        conn = sqlite3.connect('market.db')
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        c.execute("INSERT INTO transactions (user_id, type, amount) VALUES (?, ?, ?)",
                  (user_id, 'deposit', amount))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Баланс пополнен на {amount} руб.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Используйте: /confirm <сумма>")

# Команда для вывода
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(context.args[0])
        user_id = update.effective_user.id
        conn = sqlite3.connect('market.db')
        c = conn.cursor()
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        balance = c.fetchone()[0]
        if balance >= amount:
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
            c.execute("INSERT INTO transactions (user_id, type, amount) VALUES (?, ?, ?)",
                      (user_id, 'withdraw', -amount))
            conn.commit()
            await update.message.reply_text(f"✅ Выведено {amount} руб.")
        else:
            await update.message.reply_text("❌ Недостаточно средств.")
        conn.close()
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Используйте: /withdraw <сумма>")


def main():
    # Получаем токен
    TELEGRAM_BOT_TOKEN = os.getenv('TOKEN')
    print(f"🔧 Загруженный токен: {TELEGRAM_BOT_TOKEN}")
    if not TELEGRAM_BOT_TOKEN:
        print("❌ Токен не найден! Убедитесь, что файл env_var содержит TOKEN=ваш_токен")
        return

    # Создаём приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Инициализируем базу данных
    init_db()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("confirm", confirm_deposit))
    application.add_handler(CommandHandler("withdraw", withdraw))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("✅ Бот запущен и готов к работе!")
    application.run_polling()

if __name__ == '__main__':
    main()