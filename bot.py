import logging
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
USER_ID = int(os.getenv("USER_ID", "0"))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
import time
_last_clear_time = 0
scheduler = AsyncIOScheduler(timezone="Europe/Tallinn")

# --- DB ---
def init_db():
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL DEFAULT 'card',
            comment TEXT,
            created_at TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    try:
        c.execute("ALTER TABLE transactions ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'card'")
        conn.commit()
    except:
        pass
    conn.close()

def save_message_id(message_id):
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute("INSERT INTO bot_messages (message_id, created_at) VALUES (?, ?)",
              (message_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def migrate_categories():
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    migrations = [
        ("💼 Работа", "Work"),
        ("🏸 Бадминтон", "Badminton"),
        ("📦 Прочее", "Other"),
        ("🔒 Фиксированные", "Fixed"),
        ("👨‍👩‍👧 Семья", "Family"),
        ("🚗 Транспорт", "Transport"),
        ("🎯 Личное", "Personal"),
    ]
    for old_name, new_name in migrations:
        c.execute("UPDATE transactions SET category = ? WHERE category = ?", (new_name, old_name))
    conn.commit()
    conn.close()

def get_all_message_ids():
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute("SELECT message_id FROM bot_messages ORDER BY id DESC LIMIT 100")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def clear_message_ids():
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute("DELETE FROM bot_messages")
    conn.commit()
    conn.close()

def add_transaction(type_, category, amount, payment_method, comment=None):
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO transactions (type, category, amount, payment_method, comment, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (type_, category, amount, payment_method, comment, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_month_transactions(year=None, month=None):
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    prefix = f"{year}-{month:02d}"
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute(
        "SELECT * FROM transactions WHERE created_at LIKE ? ORDER BY created_at DESC",
        (f"{prefix}%",)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def delete_last_transaction():
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute("SELECT id FROM transactions ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    if row:
        c.execute("DELETE FROM transactions WHERE id = ?", (row[0],))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

# --- States ---
class AddTransaction(StatesGroup):
    waiting_amount = State()
    waiting_comment = State()

# --- Keyboards ---
INCOME_CATEGORIES = ["Work", "Badminton", "Other"]
EXPENSE_CATEGORIES = ["Fixed", "Family", "Transport", "Personal", "Other"]

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Доход", callback_data="add_income"),
            InlineKeyboardButton(text="➖ Расход", callback_data="add_expense"),
        ],
        [
            InlineKeyboardButton(text="📊 Баланс", callback_data="balance"),
            InlineKeyboardButton(text="📋 История", callback_data="history"),
        ],
        [
            InlineKeyboardButton(text="📈 Разбивка", callback_data="breakdown"),
            InlineKeyboardButton(text="🔄 Сравнение", callback_data="compare"),
        ],
        [
            InlineKeyboardButton(text="🗑 Удалить последнее", callback_data="delete_last"),
        ],
        [
            InlineKeyboardButton(text="🧹 Очистить чат", callback_data="clear_chat"),
        ]
    ])

def category_keyboard(categories, prefix):
    buttons = []
    row = []
    for i, cat in enumerate(categories):
        row.append(InlineKeyboardButton(text=cat, callback_data=f"{prefix}:{cat}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def payment_method_keyboard(prefix):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💳 Карта", callback_data=f"pm:{prefix}:card"),
            InlineKeyboardButton(text="💵 Наличные", callback_data=f"pm:{prefix}:cash"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])

def back_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В меню", callback_data="back")]
    ])

def skip_comment_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="skip_comment")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])

def reminder_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, всё внесено", callback_data="reminder_done"),
        ],
        [
            InlineKeyboardButton(text="➖ Внести расход", callback_data="add_expense"),
            InlineKeyboardButton(text="➕ Внести доход", callback_data="add_income"),
        ]
    ])

# --- Slash commands setup ---
async def set_commands():
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="menu", description="Главное меню"),
        BotCommand(command="balance", description="Баланс за месяц"),
        BotCommand(command="history", description="История транзакций"),
        BotCommand(command="breakdown", description="Разбивка по категориям"),
        BotCommand(command="compare", description="Сравнение с прошлым месяцем"),
    ]
    await bot.set_my_commands(commands)

# --- Reminder job ---
async def send_reminder():
    if USER_ID:
        await bot.send_message(
            USER_ID,
            "🔔 Привет! Ты внёс все траты за сегодня?",
            reply_markup=reminder_keyboard()
        )

# --- Handlers ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    global _last_clear_time
    if time.time() - _last_clear_time < 3:
        try:
            await message.delete()
        except:
            pass
        return
    await state.clear()
    try:
        await message.delete()
    except:
        pass
    sent = await message.answer("Главное меню:", reply_markup=main_menu())
    save_message_id(sent.message_id)

@dp.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    sent = await message.answer("Главное меню:", reply_markup=main_menu())
    save_message_id(sent.message_id)
    save_message_id(message.message_id)

@dp.message(Command("balance"))
async def cmd_balance(message: Message):
    await show_balance(message)

@dp.message(Command("history"))
async def cmd_history(message: Message):
    await show_history(message)

@dp.message(Command("breakdown"))
async def cmd_breakdown(message: Message):
    await show_breakdown(message)

@dp.message(Command("compare"))
async def cmd_compare(message: Message):
    await show_compare(message)

@dp.callback_query(F.data == "back")
async def cb_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if callback.message.photo:
        await callback.message.delete()
        sent = await bot.send_message(callback.message.chat.id, "Главное меню:", reply_markup=main_menu())
        save_message_id(sent.message_id)
    else:
        await callback.message.edit_text("Главное меню:", reply_markup=main_menu())
        save_message_id(callback.message.message_id)

@dp.callback_query(F.data == "reminder_done")
async def cb_reminder_done(callback: CallbackQuery):
    await callback.message.edit_text("👍 Отлично, так держать!")

@dp.callback_query(F.data == "add_income")
async def cb_add_income(callback: CallbackQuery):
    await callback.message.edit_text("Выбери категорию дохода:", reply_markup=category_keyboard(INCOME_CATEGORIES, "income"))

@dp.callback_query(F.data == "add_expense")
async def cb_add_expense(callback: CallbackQuery):
    await callback.message.edit_text("Выбери категорию расхода:", reply_markup=category_keyboard(EXPENSE_CATEGORIES, "expense"))

@dp.callback_query(F.data.startswith("income:"))
async def cb_income_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    await state.update_data(type="income", category=category)
    await callback.message.edit_text(
        f"Категория: {category}\n\nКак получил деньги?",
        reply_markup=payment_method_keyboard(f"income|{category}")
    )

@dp.callback_query(F.data.startswith("expense:"))
async def cb_expense_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    await state.update_data(type="expense", category=category)
    await callback.message.edit_text(
        f"Категория: {category}\n\nКак платил?",
        reply_markup=payment_method_keyboard(f"expense|{category}")
    )

@dp.callback_query(F.data.startswith("pm:"))
async def cb_payment_method(callback: CallbackQuery, state: FSMContext):
    _, prefix, method = callback.data.split(":", 2)
    type_, category = prefix.split("|", 1)
    await state.update_data(type=type_, category=category, payment_method=method)
    await state.set_state(AddTransaction.waiting_amount)
    method_text = "💳 Карта" if method == "card" else "💵 Наличные"
    await callback.message.edit_text(
        f"Категория: {category}\nСпособ: {method_text}\n\nВведи сумму в €:",
        reply_markup=back_button()
    )

@dp.message(AddTransaction.waiting_amount)
async def process_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи корректную сумму, например: 150 или 49.50")
        return
    await state.update_data(amount=amount)
    await state.set_state(AddTransaction.waiting_comment)
    await message.answer("Добавь комментарий (например, фамилию) или пропусти:", reply_markup=skip_comment_keyboard())

@dp.message(AddTransaction.waiting_comment)
async def process_comment(message: Message, state: FSMContext):
    await save_transaction(message, state, comment=message.text)

@dp.callback_query(F.data == "skip_comment", AddTransaction.waiting_comment)
async def cb_skip_comment(callback: CallbackQuery, state: FSMContext):
    await save_transaction(callback.message, state, comment=None, from_callback=True)

async def save_transaction(message, state, comment, from_callback=False):
    data = await state.get_data()
    type_ = data["type"]
    category = data["category"]
    amount = data["amount"]
    payment_method = data.get("payment_method", "card")
    add_transaction(type_, category, amount, payment_method, comment)
    await state.clear()
    sign = "+" if type_ == "income" else "-"
    method_emoji = "💳" if payment_method == "card" else "💵"
    comment_text = f" — {comment}" if comment else ""
    text = f"✅ Сохранено!\n\n{sign}{amount:.2f} € | {category} | {method_emoji}{comment_text}\n\nГлавное меню:"
    if from_callback:
        await message.edit_text(text, reply_markup=main_menu())
        save_message_id(message.message_id)
    else:
        sent = await message.answer(text, reply_markup=main_menu())
        save_message_id(sent.message_id)

# --- Report helpers ---
async def show_balance(source):
    from card import generate_balance_card
    from aiogram.types import BufferedInputFile
    rows = get_month_transactions()
    income_card = sum(r[3] for r in rows if r[1] == "income" and r[4] == "card")
    income_cash = sum(r[3] for r in rows if r[1] == "income" and r[4] == "cash")
    expense_card = sum(r[3] for r in rows if r[1] == "expense" and r[4] == "card")
    expense_cash = sum(r[3] for r in rows if r[1] == "expense" and r[4] == "cash")
    now = datetime.now()
    month_name = now.strftime("%B %Y")
    buf = generate_balance_card(income_card, income_cash, expense_card, expense_cash, month_name)
    photo = BufferedInputFile(buf.read(), filename="balance.png")
    msg = source if isinstance(source, Message) else source.message
    await msg.answer_photo(photo, reply_markup=back_button())

async def show_history(source):
    rows = get_month_transactions()
    if not rows:
        text = "📋 История пуста за этот месяц."
    else:
        lines = []
        for r in rows[:30]:
            id_, type_, cat, amount, payment_method, comment, created_at = r
            date = datetime.fromisoformat(created_at).strftime("%d.%m")
            sign = "➕" if type_ == "income" else "➖"
            method_emoji = "💳" if payment_method == "card" else "💵"
            comment_text = f" — {comment}" if comment else ""
            lines.append(f"{sign} {date}  {amount:.2f} €  {method_emoji} {cat}{comment_text}")
        text = "📋 <b>История за этот месяц:</b>\n\n" + "\n".join(lines)
        if len(rows) > 30:
            text += f"\n\n...и ещё {len(rows) - 30} записей"
    if isinstance(source, Message):
        await source.answer(text, reply_markup=back_button(), parse_mode="HTML")
    else:
        await source.message.edit_text(text, reply_markup=back_button(), parse_mode="HTML")

async def show_breakdown(source):
    from card import generate_breakdown_card
    from aiogram.types import BufferedInputFile
    rows = get_month_transactions()
    if not rows:
        msg = source if isinstance(source, Message) else source.message
        await msg.answer("📈 Нет данных за этот месяц.", reply_markup=back_button())
        return
    expense_rows = [r for r in rows if r[1] == "expense"]
    income_rows = [r for r in rows if r[1] == "income"]
    total_expense = sum(r[3] for r in expense_rows)
    total_income = sum(r[3] for r in income_rows)
    exp_by_cat = {}
    for r in expense_rows:
        exp_by_cat[r[2]] = exp_by_cat.get(r[2], 0) + r[3]
    inc_by_cat = {}
    for r in income_rows:
        inc_by_cat[r[2]] = inc_by_cat.get(r[2], 0) + r[3]
    now = datetime.now()
    month_name = now.strftime("%B %Y")
    buf = generate_breakdown_card(inc_by_cat, exp_by_cat, total_income, total_expense, month_name)
    photo = BufferedInputFile(buf.read(), filename="breakdown.png")
    msg = source if isinstance(source, Message) else source.message
    await msg.answer_photo(photo, reply_markup=back_button())

async def show_compare(source):
    now = datetime.now()
    cur_month = now.month
    cur_year = now.year
    prev_month = cur_month - 1 if cur_month > 1 else 12
    prev_year = cur_year if cur_month > 1 else cur_year - 1
    cur_rows = get_month_transactions(cur_year, cur_month)
    prev_rows = get_month_transactions(prev_year, prev_month)

    def by_cat(rows, type_):
        d = {}
        for r in rows:
            if r[1] == type_:
                d[r[2]] = d.get(r[2], 0) + r[3]
        return d

    cur_exp = by_cat(cur_rows, "expense")
    prev_exp = by_cat(prev_rows, "expense")
    cur_inc = by_cat(cur_rows, "income")
    prev_inc = by_cat(prev_rows, "income")
    all_exp_cats = set(list(cur_exp.keys()) + list(prev_exp.keys()))
    all_inc_cats = set(list(cur_inc.keys()) + list(prev_inc.keys()))
    cur_month_name = now.strftime("%b")
    prev_month_name = datetime(prev_year, prev_month, 1).strftime("%b")
    lines = [f"🔄 <b>Сравнение {prev_month_name} → {cur_month_name}:</b>\n"]
    lines.append("💰 <b>Доходы:</b>")
    for cat in sorted(all_inc_cats):
        c = cur_inc.get(cat, 0)
        p = prev_inc.get(cat, 0)
        delta = c - p
        delta_text = f"  <b>({'+' if delta >= 0 else ''}{delta:.0f})</b>" if delta != 0 else ""
        lines.append(f"  {cat}: {p:.0f} → {c:.0f} €{delta_text}")
    lines.append("\n💸 <b>Расходы:</b>")
    for cat in sorted(all_exp_cats):
        c = cur_exp.get(cat, 0)
        p = prev_exp.get(cat, 0)
        delta = c - p
        delta_text = f"  <b>({'+' if delta >= 0 else ''}{delta:.0f})</b>" if delta != 0 else ""
        lines.append(f"  {cat}: {p:.0f} → {c:.0f} €{delta_text}")
    cur_inc_total = sum(cur_inc.values())
    prev_inc_total = sum(prev_inc.values())
    delta_inc = cur_inc_total - prev_inc_total
    lines.append(f"\n<b>Итого доходы: {prev_inc_total:.0f} → {cur_inc_total:.0f} € ({'+' if delta_inc >= 0 else ''}{delta_inc:.0f})</b>")

    cur_exp_total = sum(cur_exp.values())
    prev_exp_total = sum(prev_exp.values())
    delta_exp = cur_exp_total - prev_exp_total
    lines.append(f"<b>Итого расходы: {prev_exp_total:.0f} → {cur_exp_total:.0f} € ({'+' if delta_exp >= 0 else ''}{delta_exp:.0f})</b>")

    prev_balance = prev_inc_total - prev_exp_total
    cur_balance = cur_inc_total - cur_exp_total
    delta_balance = cur_balance - prev_balance
    lines.append(f"\n💰 <b>Остаток: {prev_balance:.0f} → {cur_balance:.0f} € ({'+' if delta_balance >= 0 else ''}{delta_balance:.0f})</b>")
    text = "\n".join(lines)
    if isinstance(source, Message):
        await source.answer(text, reply_markup=back_button(), parse_mode="HTML")
    else:
        await source.message.edit_text(text, reply_markup=back_button(), parse_mode="HTML")

@dp.callback_query(F.data == "balance")
async def cb_balance(callback: CallbackQuery):
    await show_balance(callback)

@dp.callback_query(F.data == "history")
async def cb_history(callback: CallbackQuery):
    await show_history(callback)

@dp.callback_query(F.data == "breakdown")
async def cb_breakdown(callback: CallbackQuery):
    await show_breakdown(callback)

@dp.callback_query(F.data == "compare")
async def cb_compare(callback: CallbackQuery):
    await show_compare(callback)

@dp.callback_query(F.data == "delete_last")
async def cb_delete_last(callback: CallbackQuery):
    success = delete_last_transaction()
    if success:
        await callback.message.edit_text("🗑 Последняя запись удалена.\n\nГлавное меню:", reply_markup=main_menu())
    else:
        await callback.message.edit_text("❌ Нет записей для удаления.", reply_markup=main_menu())

@dp.callback_query(F.data == "clear_chat")
async def cb_clear_chat(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    chat_id = callback.message.chat.id
    current_id = callback.message.message_id
    # Delete last 50 messages by trying IDs downward
    for msg_id in range(current_id, max(current_id - 200, 0), -1):
        try:
            await bot.delete_message(chat_id, msg_id)
        except:
            pass
    sent = await bot.send_message(chat_id, "Главное меню:", reply_markup=main_menu())
    save_message_id(sent.message_id)

# --- Main ---
async def main():
    init_db()
    migrate_categories()
    await set_commands()
    scheduler.add_job(send_reminder, "cron", hour=22, minute=0)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())        ("👨‍👩‍👧 Семья", "Family"),
        ("🚗 Транспорт", "Transport"),
        ("🎯 Личное", "Personal"),
    ]
    for old_name, new_name in migrations:
        c.execute("UPDATE transactions SET category = ? WHERE category = ?", (new_name, old_name))
    conn.commit()
    conn.close()

def get_all_message_ids():
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute("SELECT message_id FROM bot_messages ORDER BY id DESC LIMIT 100")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def clear_message_ids():
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute("DELETE FROM bot_messages")
    conn.commit()
    conn.close()

def add_transaction(type_, category, amount, payment_method, comment=None):
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO transactions (type, category, amount, payment_method, comment, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (type_, category, amount, payment_method, comment, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_month_transactions(year=None, month=None):
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    prefix = f"{year}-{month:02d}"
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute(
        "SELECT * FROM transactions WHERE created_at LIKE ? ORDER BY created_at DESC",
        (f"{prefix}%",)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def delete_last_transaction():
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute("SELECT id FROM transactions ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    if row:
        c.execute("DELETE FROM transactions WHERE id = ?", (row[0],))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

# --- States ---
class AddTransaction(StatesGroup):
    waiting_amount = State()
    waiting_comment = State()

# --- Keyboards ---
INCOME_CATEGORIES = ["Work", "Badminton", "Other"]
EXPENSE_CATEGORIES = ["Fixed", "Family", "Transport", "Personal", "Other"]

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Доход", callback_data="add_income"),
            InlineKeyboardButton(text="➖ Расход", callback_data="add_expense"),
        ],
        [
            InlineKeyboardButton(text="📊 Баланс", callback_data="balance"),
            InlineKeyboardButton(text="📋 История", callback_data="history"),
        ],
        [
            InlineKeyboardButton(text="📈 Разбивка", callback_data="breakdown"),
            InlineKeyboardButton(text="🔄 Сравнение", callback_data="compare"),
        ],
        [
            InlineKeyboardButton(text="🗑 Удалить последнее", callback_data="delete_last"),
        ],
        [
            InlineKeyboardButton(text="🧹 Очистить чат", callback_data="clear_chat"),
        ]
    ])

def category_keyboard(categories, prefix):
    buttons = []
    row = []
    for i, cat in enumerate(categories):
        row.append(InlineKeyboardButton(text=cat, callback_data=f"{prefix}:{cat}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def payment_method_keyboard(prefix):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💳 Карта", callback_data=f"pm:{prefix}:card"),
            InlineKeyboardButton(text="💵 Наличные", callback_data=f"pm:{prefix}:cash"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])

def back_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В меню", callback_data="back")]
    ])

def skip_comment_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="skip_comment")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])

def reminder_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, всё внесено", callback_data="reminder_done"),
        ],
        [
            InlineKeyboardButton(text="➖ Внести расход", callback_data="add_expense"),
            InlineKeyboardButton(text="➕ Внести доход", callback_data="add_income"),
        ]
    ])

# --- Slash commands setup ---
async def set_commands():
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="menu", description="Главное меню"),
        BotCommand(command="balance", description="Баланс за месяц"),
        BotCommand(command="history", description="История транзакций"),
        BotCommand(command="breakdown", description="Разбивка по категориям"),
        BotCommand(command="compare", description="Сравнение с прошлым месяцем"),
    ]
    await bot.set_my_commands(commands)

# --- Reminder job ---
async def send_reminder():
    if USER_ID:
        await bot.send_message(
            USER_ID,
            "🔔 Привет! Ты внёс все траты за сегодня?",
            reply_markup=reminder_keyboard()
        )

# --- Handlers ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    global _last_clear_time
    if time.time() - _last_clear_time < 3:
        try:
            await message.delete()
        except:
            pass
        return
    await state.clear()
    try:
        await message.delete()
    except:
        pass
    sent = await message.answer("👋 Привет! Я твой финансовый трекер.\n\nВыбери действие:", reply_markup=main_menu())
    save_message_id(sent.message_id)

@dp.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    sent = await message.answer("Главное меню:", reply_markup=main_menu())
    save_message_id(sent.message_id)
    save_message_id(message.message_id)

@dp.message(Command("balance"))
async def cmd_balance(message: Message):
    await show_balance(message)

@dp.message(Command("history"))
async def cmd_history(message: Message):
    await show_history(message)

@dp.message(Command("breakdown"))
async def cmd_breakdown(message: Message):
    await show_breakdown(message)

@dp.message(Command("compare"))
async def cmd_compare(message: Message):
    await show_compare(message)

@dp.callback_query(F.data == "back")
async def cb_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if callback.message.photo:
        await callback.message.delete()
        sent = await bot.send_message(callback.message.chat.id, "Главное меню:", reply_markup=main_menu())
        save_message_id(sent.message_id)
    else:
        await callback.message.edit_text("Главное меню:", reply_markup=main_menu())
        save_message_id(callback.message.message_id)

@dp.callback_query(F.data == "reminder_done")
async def cb_reminder_done(callback: CallbackQuery):
    await callback.message.edit_text("👍 Отлично, так держать!")

@dp.callback_query(F.data == "add_income")
async def cb_add_income(callback: CallbackQuery):
    await callback.message.edit_text("Выбери категорию дохода:", reply_markup=category_keyboard(INCOME_CATEGORIES, "income"))

@dp.callback_query(F.data == "add_expense")
async def cb_add_expense(callback: CallbackQuery):
    await callback.message.edit_text("Выбери категорию расхода:", reply_markup=category_keyboard(EXPENSE_CATEGORIES, "expense"))

@dp.callback_query(F.data.startswith("income:"))
async def cb_income_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    await state.update_data(type="income", category=category)
    await callback.message.edit_text(
        f"Категория: {category}\n\nКак получил деньги?",
        reply_markup=payment_method_keyboard(f"income|{category}")
    )

@dp.callback_query(F.data.startswith("expense:"))
async def cb_expense_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    await state.update_data(type="expense", category=category)
    await callback.message.edit_text(
        f"Категория: {category}\n\nКак платил?",
        reply_markup=payment_method_keyboard(f"expense|{category}")
    )

@dp.callback_query(F.data.startswith("pm:"))
async def cb_payment_method(callback: CallbackQuery, state: FSMContext):
    _, prefix, method = callback.data.split(":", 2)
    type_, category = prefix.split("|", 1)
    await state.update_data(type=type_, category=category, payment_method=method)
    await state.set_state(AddTransaction.waiting_amount)
    method_text = "💳 Карта" if method == "card" else "💵 Наличные"
    await callback.message.edit_text(
        f"Категория: {category}\nСпособ: {method_text}\n\nВведи сумму в €:",
        reply_markup=back_button()
    )

@dp.message(AddTransaction.waiting_amount)
async def process_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи корректную сумму, например: 150 или 49.50")
        return
    await state.update_data(amount=amount)
    await state.set_state(AddTransaction.waiting_comment)
    await message.answer("Добавь комментарий (например, фамилию) или пропусти:", reply_markup=skip_comment_keyboard())

@dp.message(AddTransaction.waiting_comment)
async def process_comment(message: Message, state: FSMContext):
    await save_transaction(message, state, comment=message.text)

@dp.callback_query(F.data == "skip_comment", AddTransaction.waiting_comment)
async def cb_skip_comment(callback: CallbackQuery, state: FSMContext):
    await save_transaction(callback.message, state, comment=None, from_callback=True)

async def save_transaction(message, state, comment, from_callback=False):
    data = await state.get_data()
    type_ = data["type"]
    category = data["category"]
    amount = data["amount"]
    payment_method = data.get("payment_method", "card")
    add_transaction(type_, category, amount, payment_method, comment)
    await state.clear()
    sign = "+" if type_ == "income" else "-"
    method_emoji = "💳" if payment_method == "card" else "💵"
    comment_text = f" — {comment}" if comment else ""
    text = f"✅ Сохранено!\n\n{sign}{amount:.2f} € | {category} | {method_emoji}{comment_text}\n\nГлавное меню:"
    if from_callback:
        await message.edit_text(text, reply_markup=main_menu())
        save_message_id(message.message_id)
    else:
        sent = await message.answer(text, reply_markup=main_menu())
        save_message_id(sent.message_id)

# --- Report helpers ---
async def show_balance(source):
    from card import generate_balance_card
    from aiogram.types import BufferedInputFile
    rows = get_month_transactions()
    income_card = sum(r[3] for r in rows if r[1] == "income" and r[4] == "card")
    income_cash = sum(r[3] for r in rows if r[1] == "income" and r[4] == "cash")
    expense_card = sum(r[3] for r in rows if r[1] == "expense" and r[4] == "card")
    expense_cash = sum(r[3] for r in rows if r[1] == "expense" and r[4] == "cash")
    now = datetime.now()
    month_name = now.strftime("%B %Y")
    buf = generate_balance_card(income_card, income_cash, expense_card, expense_cash, month_name)
    photo = BufferedInputFile(buf.read(), filename="balance.png")
    msg = source if isinstance(source, Message) else source.message
    await msg.answer_photo(photo, reply_markup=back_button())

async def show_history(source):
    rows = get_month_transactions()
    if not rows:
        text = "📋 История пуста за этот месяц."
    else:
        lines = []
        for r in rows[:30]:
            id_, type_, cat, amount, payment_method, comment, created_at = r
            date = datetime.fromisoformat(created_at).strftime("%d.%m")
            sign = "➕" if type_ == "income" else "➖"
            method_emoji = "💳" if payment_method == "card" else "💵"
            comment_text = f" — {comment}" if comment else ""
            lines.append(f"{sign} {date}  {amount:.2f} €  {method_emoji} {cat}{comment_text}")
        text = "📋 <b>История за этот месяц:</b>\n\n" + "\n".join(lines)
        if len(rows) > 30:
            text += f"\n\n...и ещё {len(rows) - 30} записей"
    if isinstance(source, Message):
        await source.answer(text, reply_markup=back_button(), parse_mode="HTML")
    else:
        await source.message.edit_text(text, reply_markup=back_button(), parse_mode="HTML")

async def show_breakdown(source):
    from card import generate_breakdown_card
    from aiogram.types import BufferedInputFile
    rows = get_month_transactions()
    if not rows:
        msg = source if isinstance(source, Message) else source.message
        await msg.answer("📈 Нет данных за этот месяц.", reply_markup=back_button())
        return
    expense_rows = [r for r in rows if r[1] == "expense"]
    income_rows = [r for r in rows if r[1] == "income"]
    total_expense = sum(r[3] for r in expense_rows)
    total_income = sum(r[3] for r in income_rows)
    exp_by_cat = {}
    for r in expense_rows:
        exp_by_cat[r[2]] = exp_by_cat.get(r[2], 0) + r[3]
    inc_by_cat = {}
    for r in income_rows:
        inc_by_cat[r[2]] = inc_by_cat.get(r[2], 0) + r[3]
    now = datetime.now()
    month_name = now.strftime("%B %Y")
    buf = generate_breakdown_card(inc_by_cat, exp_by_cat, total_income, total_expense, month_name)
    photo = BufferedInputFile(buf.read(), filename="breakdown.png")
    msg = source if isinstance(source, Message) else source.message
    await msg.answer_photo(photo, reply_markup=back_button())

async def show_compare(source):
    now = datetime.now()
    cur_month = now.month
    cur_year = now.year
    prev_month = cur_month - 1 if cur_month > 1 else 12
    prev_year = cur_year if cur_month > 1 else cur_year - 1
    cur_rows = get_month_transactions(cur_year, cur_month)
    prev_rows = get_month_transactions(prev_year, prev_month)

    def by_cat(rows, type_):
        d = {}
        for r in rows:
            if r[1] == type_:
                d[r[2]] = d.get(r[2], 0) + r[3]
        return d

    cur_exp = by_cat(cur_rows, "expense")
    prev_exp = by_cat(prev_rows, "expense")
    cur_inc = by_cat(cur_rows, "income")
    prev_inc = by_cat(prev_rows, "income")
    all_exp_cats = set(list(cur_exp.keys()) + list(prev_exp.keys()))
    all_inc_cats = set(list(cur_inc.keys()) + list(prev_inc.keys()))
    cur_month_name = now.strftime("%b")
    prev_month_name = datetime(prev_year, prev_month, 1).strftime("%b")
    lines = [f"🔄 <b>Сравнение {prev_month_name} → {cur_month_name}:</b>\n"]
    lines.append("💰 <b>Доходы:</b>")
    for cat in sorted(all_inc_cats):
        c = cur_inc.get(cat, 0)
        p = prev_inc.get(cat, 0)
        delta = c - p
        delta_text = f"  <b>({'+' if delta >= 0 else ''}{delta:.0f})</b>" if delta != 0 else ""
        lines.append(f"  {cat}: {p:.0f} → {c:.0f} €{delta_text}")
    lines.append("\n💸 <b>Расходы:</b>")
    for cat in sorted(all_exp_cats):
        c = cur_exp.get(cat, 0)
        p = prev_exp.get(cat, 0)
        delta = c - p
        delta_text = f"  <b>({'+' if delta >= 0 else ''}{delta:.0f})</b>" if delta != 0 else ""
        lines.append(f"  {cat}: {p:.0f} → {c:.0f} €{delta_text}")
    cur_inc_total = sum(cur_inc.values())
    prev_inc_total = sum(prev_inc.values())
    delta_inc = cur_inc_total - prev_inc_total
    lines.append(f"\n<b>Итого доходы: {prev_inc_total:.0f} → {cur_inc_total:.0f} € ({'+' if delta_inc >= 0 else ''}{delta_inc:.0f})</b>")

    cur_exp_total = sum(cur_exp.values())
    prev_exp_total = sum(prev_exp.values())
    delta_exp = cur_exp_total - prev_exp_total
    lines.append(f"<b>Итого расходы: {prev_exp_total:.0f} → {cur_exp_total:.0f} € ({'+' if delta_exp >= 0 else ''}{delta_exp:.0f})</b>")

    prev_balance = prev_inc_total - prev_exp_total
    cur_balance = cur_inc_total - cur_exp_total
    delta_balance = cur_balance - prev_balance
    lines.append(f"\n💰 <b>Остаток: {prev_balance:.0f} → {cur_balance:.0f} € ({'+' if delta_balance >= 0 else ''}{delta_balance:.0f})</b>")
    text = "\n".join(lines)
    if isinstance(source, Message):
        await source.answer(text, reply_markup=back_button(), parse_mode="HTML")
    else:
        await source.message.edit_text(text, reply_markup=back_button(), parse_mode="HTML")

@dp.callback_query(F.data == "balance")
async def cb_balance(callback: CallbackQuery):
    await show_balance(callback)

@dp.callback_query(F.data == "history")
async def cb_history(callback: CallbackQuery):
    await show_history(callback)

@dp.callback_query(F.data == "breakdown")
async def cb_breakdown(callback: CallbackQuery):
    await show_breakdown(callback)

@dp.callback_query(F.data == "compare")
async def cb_compare(callback: CallbackQuery):
    await show_compare(callback)

@dp.callback_query(F.data == "delete_last")
async def cb_delete_last(callback: CallbackQuery):
    success = delete_last_transaction()
    if success:
        await callback.message.edit_text("🗑 Последняя запись удалена.\n\nГлавное меню:", reply_markup=main_menu())
    else:
        await callback.message.edit_text("❌ Нет записей для удаления.", reply_markup=main_menu())

@dp.callback_query(F.data == "clear_chat")
async def cb_clear_chat(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    chat_id = callback.message.chat.id
    current_id = callback.message.message_id
    # Delete last 50 messages by trying IDs downward
    for msg_id in range(current_id, max(current_id - 50, 0), -1):
        try:
            await bot.delete_message(chat_id, msg_id)
        except:
            pass
    sent = await bot.send_message(chat_id, "Главное меню:", reply_markup=main_menu())
    save_message_id(sent.message_id)

# --- Main ---
async def main():
    init_db()
    migrate_categories()
    await set_commands()
    scheduler.add_job(send_reminder, "cron", hour=22, minute=0)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
