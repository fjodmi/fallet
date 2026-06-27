import logging
import sqlite3
import time
import zoneinfo
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
scheduler = AsyncIOScheduler(timezone="Europe/Tallinn")
_last_clear_time = 0

INCOME_CATEGORIES = ["Work", "Badminton", "Other"]
EXPENSE_CATEGORIES = ["Fixed", "Family", "Transport", "Personal", "Other"]

def init_db():
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        payment_method TEXT NOT NULL DEFAULT 'card',
        comment TEXT,
        created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS bot_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )""")
    try:
        c.execute("ALTER TABLE transactions ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'card'")
        conn.commit()
    except:
        pass
    conn.close()

def add_transaction(type_, category, amount, payment_method, comment=None):
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute("INSERT INTO transactions (type, category, amount, payment_method, comment, created_at) VALUES (?, ?, ?, ?, ?, ?)",
              (type_, category, amount, payment_method, comment, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_month_transactions(year=None, month=None):
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    prefix = f"{year}-{month:02d}"
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute("SELECT * FROM transactions WHERE created_at LIKE ? ORDER BY created_at DESC", (f"{prefix}%",))
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

def get_last_transaction():
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute("SELECT * FROM transactions ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row

def update_transaction(id_, **kwargs):
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    for field, value in kwargs.items():
        c.execute(f"UPDATE transactions SET {field} = ? WHERE id = ?", (value, id_))
    conn.commit()
    conn.close()

def save_message_id(message_id):
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute("INSERT INTO bot_messages (message_id, created_at) VALUES (?, ?)",
              (message_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def clear_message_ids():
    conn = sqlite3.connect("/data/budget.db")
    c = conn.cursor()
    c.execute("DELETE FROM bot_messages")
    conn.commit()
    conn.close()

class AddTransaction(StatesGroup):
    waiting_amount = State()
    waiting_comment = State()

class EditTransaction(StatesGroup):
    choosing_field = State()
    waiting_new_amount = State()
    waiting_new_comment = State()

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Доход", callback_data="add_income"),
         InlineKeyboardButton(text="➖ Расход", callback_data="add_expense")],
        [InlineKeyboardButton(text="📊 Баланс", callback_data="balance"),
         InlineKeyboardButton(text="📋 История", callback_data="history")],
        [InlineKeyboardButton(text="📈 Разбивка", callback_data="breakdown"),
         InlineKeyboardButton(text="🔄 Сравнение", callback_data="compare")],
        [InlineKeyboardButton(text="🗑 Удалить последнее", callback_data="delete_last"),
         InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_last")],
        [InlineKeyboardButton(text="🧹 Очистить чат", callback_data="clear_chat")],
    ])

def category_keyboard(categories, prefix):
    buttons = []
    row = []
    for cat in categories:
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
        [InlineKeyboardButton(text="💳 Карта", callback_data=f"pm:{prefix}:card"),
         InlineKeyboardButton(text="💵 Наличные", callback_data=f"pm:{prefix}:cash")],
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
        [InlineKeyboardButton(text="✅ Да, всё внесено", callback_data="reminder_done")],
        [InlineKeyboardButton(text="➖ Внести расход", callback_data="add_expense"),
         InlineKeyboardButton(text="➕ Внести доход", callback_data="add_income")],
    ])

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

async def send_reminder():
    if USER_ID:
        await bot.send_message(USER_ID, "🔔 Привет! Ты внёс все траты за сегодня?", reply_markup=reminder_keyboard())

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    global _last_clear_time
    try:
        await message.delete()
    except:
        pass
    if time.time() - _last_clear_time < 3:
        return
    await state.clear()
    sent = await bot.send_message(message.chat.id, "Главное меню:", reply_markup=main_menu())
    save_message_id(sent.message_id)

@dp.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    try:
        await message.delete()
    except:
        pass
    sent = await bot.send_message(message.chat.id, "Главное меню:", reply_markup=main_menu())
    save_message_id(sent.message_id)

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
    await callback.message.edit_text(f"Категория: {category}\n\nКак получил деньги?",
                                     reply_markup=payment_method_keyboard(f"income|{category}"))

@dp.callback_query(F.data.startswith("expense:"))
async def cb_expense_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    await state.update_data(type="expense", category=category)
    await callback.message.edit_text(f"Категория: {category}\n\nКак платил?",
                                     reply_markup=payment_method_keyboard(f"expense|{category}"))

@dp.callback_query(F.data.startswith("pm:"))
async def cb_payment_method(callback: CallbackQuery, state: FSMContext):
    _, prefix, method = callback.data.split(":", 2)
    type_, category = prefix.split("|", 1)
    await state.update_data(type=type_, category=category, payment_method=method)
    await state.set_state(AddTransaction.waiting_amount)
    method_text = "💳 Карта" if method == "card" else "💵 Наличные"
    await callback.message.edit_text(f"Категория: {category}\nСпособ: {method_text}\n\nВведи сумму в €:",
                                     reply_markup=back_button())

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
    sent = await message.answer("Добавь комментарий (например, фамилию) или пропусти:", reply_markup=skip_comment_keyboard())
    save_message_id(sent.message_id)
    save_message_id(message.message_id)

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
    from card import generate_history_card
    from aiogram.types import BufferedInputFile
    rows = get_month_transactions()
    if not rows:
        msg = source if isinstance(source, Message) else source.message
        await msg.answer("📋 История пуста за этот месяц.", reply_markup=back_button())
        return
    now = datetime.now()
    month_name = now.strftime("%B %Y")
    buf = generate_history_card(rows, month_name)
    photo = BufferedInputFile(buf.read(), filename="history.png")
    msg = source if isinstance(source, Message) else source.message
    await msg.answer_photo(photo, reply_markup=back_button())

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
    from card import generate_compare_card
    from aiogram.types import BufferedInputFile
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
    cur_month_name = now.strftime("%b")
    prev_month_name = datetime(prev_year, prev_month, 1).strftime("%b")
    buf = generate_compare_card(cur_inc, prev_inc, cur_exp, prev_exp, cur_month_name, prev_month_name)
    photo = BufferedInputFile(buf.read(), filename="compare.png")
    msg = source if isinstance(source, Message) else source.message
    await msg.answer_photo(photo, reply_markup=back_button())

@dp.callback_query(F.data == "balance")
async def cb_balance(callback: CallbackQuery):
    await callback.answer()
    await show_balance(callback)

@dp.callback_query(F.data == "history")
async def cb_history(callback: CallbackQuery):
    await callback.answer()
    await show_history(callback)

@dp.callback_query(F.data == "breakdown")
async def cb_breakdown(callback: CallbackQuery):
    await callback.answer()
    await show_breakdown(callback)

@dp.callback_query(F.data == "compare")
async def cb_compare(callback: CallbackQuery):
    await callback.answer()
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
    global _last_clear_time
    await callback.answer()
    await state.clear()
    chat_id = callback.message.chat.id
    current_id = callback.message.message_id
    for msg_id in range(current_id, max(current_id - 200, 0), -1):
        try:
            await bot.delete_message(chat_id, msg_id)
        except:
            pass
    _last_clear_time = time.time()
    sent = await bot.send_message(chat_id, "Главное меню:", reply_markup=main_menu())
    save_message_id(sent.message_id)



# --- Edit last transaction ---
def edit_field_keyboard(tx_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Сумма", callback_data=f"edit_field:{tx_id}:amount"),
         InlineKeyboardButton(text="📂 Категория", callback_data=f"edit_field:{tx_id}:category")],
        [InlineKeyboardButton(text="💳 Метод", callback_data=f"edit_field:{tx_id}:method"),
         InlineKeyboardButton(text="💬 Комментарий", callback_data=f"edit_field:{tx_id}:comment")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])

@dp.callback_query(F.data == "edit_last")
async def cb_edit_last(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    row = get_last_transaction()
    if not row:
        await callback.message.edit_text("❌ Нет транзакций для редактирования.", reply_markup=main_menu())
        return
    id_, type_, cat, amount, payment_method, comment, created_at = row
    sign = "+" if type_ == "income" else "-"
    method_text = "💳 Карта" if payment_method == "card" else "💵 Наличные"
    comment_text = f" — {comment}" if comment else ""
    text = (f"✏️ <b>Последняя транзакция:</b>\n\n"
            f"{sign}{amount:.2f} € | {cat} | {method_text}{comment_text}\n\n"
            f"Что хочешь изменить?")
    await callback.message.edit_text(text, reply_markup=edit_field_keyboard(id_), parse_mode="HTML")
    await state.set_state(EditTransaction.choosing_field)

@dp.callback_query(F.data.startswith("edit_field:"))
async def cb_edit_field(callback: CallbackQuery, state: FSMContext):
    _, tx_id, field = callback.data.split(":")
    await state.update_data(tx_id=int(tx_id), field=field)

    if field == "amount":
        await state.set_state(EditTransaction.waiting_new_amount)
        await callback.message.edit_text("Введи новую сумму в €:", reply_markup=back_button())

    elif field == "category":
        row = get_last_transaction()
        type_ = row[1]
        cats = INCOME_CATEGORIES if type_ == "income" else EXPENSE_CATEGORIES
        prefix = f"edit_cat:{tx_id}"
        await callback.message.edit_text("Выбери новую категорию:",
                                          reply_markup=category_keyboard(cats, prefix))

    elif field == "method":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Карта", callback_data=f"edit_method:{tx_id}:card"),
             InlineKeyboardButton(text="💵 Наличные", callback_data=f"edit_method:{tx_id}:cash")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
        ])
        await callback.message.edit_text("Выбери способ оплаты:", reply_markup=kb)

    elif field == "comment":
        await state.set_state(EditTransaction.waiting_new_comment)
        await callback.message.edit_text("Введи новый комментарий или напиши 'нет' чтобы удалить:",
                                          reply_markup=back_button())

@dp.callback_query(F.data.startswith("edit_cat:"))
async def cb_edit_cat(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":", 2)
    tx_id = int(parts[1])
    category = parts[2]
    update_transaction(tx_id, category=category)
    await state.clear()
    await callback.message.edit_text(f"✅ Категория изменена на {category}\n\nГлавное меню:", reply_markup=main_menu())

@dp.callback_query(F.data.startswith("edit_method:"))
async def cb_edit_method(callback: CallbackQuery, state: FSMContext):
    _, tx_id, method = callback.data.split(":")
    update_transaction(int(tx_id), payment_method=method)
    await state.clear()
    method_text = "💳 Карта" if method == "card" else "💵 Наличные"
    await callback.message.edit_text(f"✅ Метод изменён на {method_text}\n\nГлавное меню:", reply_markup=main_menu())

@dp.message(EditTransaction.waiting_new_amount)
async def process_edit_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи корректную сумму, например: 150 или 49.50")
        return
    data = await state.get_data()
    update_transaction(data["tx_id"], amount=amount)
    await state.clear()
    try:
        await message.delete()
    except:
        pass
    sent = await message.answer(f"✅ Сумма изменена на {amount:.2f} €\n\nГлавное меню:", reply_markup=main_menu())
    save_message_id(sent.message_id)

@dp.message(EditTransaction.waiting_new_comment)
async def process_edit_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    new_comment = None if message.text.lower() in ["нет", "no", "-"] else message.text
    update_transaction(data["tx_id"], comment=new_comment)
    await state.clear()
    try:
        await message.delete()
    except:
        pass
    comment_text = f"«{new_comment}»" if new_comment else "удалён"
    sent = await message.answer(f"✅ Комментарий {comment_text}\n\nГлавное меню:", reply_markup=main_menu())
    save_message_id(sent.message_id)

# --- AI free text handler ---
async def parse_transaction_with_ai(text: str) -> dict | None:
    import json
    import aiohttp
    
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    if not ANTHROPIC_API_KEY:
        return None

    system_prompt = """You are a financial transaction parser. 
The user will describe a transaction in free form (Russian or English).
Extract and return ONLY a JSON object with these fields:
- type: "income" or "expense"
- category: one of ["Work", "Badminton", "Other"] for income, or ["Fixed", "Family", "Transport", "Personal", "Other"] for expense
- amount: number (positive)
- payment_method: "card" or "cash"
- comment: string or null (name, note, etc.)

Rules:
- бензин/топливо/заправка → expense, Transport
- еда/обед/кофе/ресторан → expense, Personal
- тренировка/урок/ученик → income, Badminton
- зарплата/работа → income, Work
- нал/наличные/cash → cash, otherwise card
- если не уверен в payment_method → card

Return ONLY valid JSON, no explanation, no markdown."""

    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 200,
        "system": system_prompt,
        "messages": [{"role": "user", "content": text}]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json=payload
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            raw = data["content"][0]["text"].strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(raw)


@dp.message(F.text & ~F.text.startswith("/"))
async def handle_free_text(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return

    processing = await message.answer("⏳ Обрабатываю...")
    save_message_id(message.message_id)

    try:
        result = await parse_transaction_with_ai(message.text)
    except Exception:
        result = None

    await processing.delete()

    if not result or "amount" not in result:
        sent = await message.answer(
            "❌ Не смог распознать транзакцию. Попробуй написать иначе, например:\n"
            "<i>бензин 45 картой</i> или <i>получил 200 нал от Петрова</i>",
            reply_markup=back_button(),
            parse_mode="HTML"
        )
        save_message_id(sent.message_id)
        return

    type_ = result.get("type", "expense")
    category = result.get("category", "Other")
    amount = float(result.get("amount", 0))
    payment_method = result.get("payment_method", "card")
    comment = result.get("comment")

    add_transaction(type_, category, amount, payment_method, comment)

    sign = "+" if type_ == "income" else "-"
    method_emoji = "💳" if payment_method == "card" else "💵"
    comment_text = f" — {comment}" if comment else ""

    sent = await message.answer(
        f"✅ Сохранено!\n\n{sign}{amount:.2f} € | {category} | {method_emoji}{comment_text}\n\nГлавное меню:",
        reply_markup=main_menu()
    )
    save_message_id(sent.message_id)

async def main():
    init_db()
    await set_commands()
    scheduler.add_job(send_reminder, "cron", hour=22, minute=0)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
