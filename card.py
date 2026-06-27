from PIL import Image, ImageDraw, ImageFont
import io
from datetime import datetime

# Colors
BG = "#F2EEE4"
TEXT_DARK = "#2C2C2C"
TEXT_MUTED = "#8C8680"
INCOME_COLOR = "#4A7C59"
EXPENSE_COLOR = "#FF5A5A"
DIVIDER = "#DDD8CE"
CARD_BG = "#EBE7DC"

FONT_PATH = "fonts/Inter.ttf"

def load_font(size, bold=False):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except:
        return ImageFont.load_default()

def draw_rounded_rect(draw, xy, radius, fill):
    x1, y1, x2, y2 = xy
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    draw.ellipse([x1, y1, x1 + radius * 2, y1 + radius * 2], fill=fill)
    draw.ellipse([x2 - radius * 2, y1, x2, y1 + radius * 2], fill=fill)
    draw.ellipse([x1, y2 - radius * 2, x1 + radius * 2, y2], fill=fill)
    draw.ellipse([x2 - radius * 2, y2 - radius * 2, x2, y2], fill=fill)

def generate_balance_card(income_card, income_cash, expense_card, expense_cash, month_name):
    W, H = 720, 520
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    total_income = income_card + income_cash
    total_expense = expense_card + expense_cash
    balance = total_income - total_expense

    # Fonts
    f_small = load_font(22)
    f_medium = load_font(28)
    f_large = load_font(52)
    f_label = load_font(19)

    PAD = 48

    # Month label
    draw.text((PAD, PAD), month_name.upper(), font=f_label, fill=TEXT_MUTED)

    # Balance
    balance_text = f"{'+' if balance >= 0 else ''}{balance:,.2f} €"
    balance_color = INCOME_COLOR if balance >= 0 else EXPENSE_COLOR
    draw.text((PAD, PAD + 36), "Остаток", font=f_medium, fill=TEXT_MUTED)
    draw.text((PAD, PAD + 70), balance_text, font=f_large, fill=balance_color)

    # Divider
    y_div = PAD + 145
    draw.rectangle([PAD, y_div, W - PAD, y_div + 1], fill=DIVIDER)

    # Income block
    y = y_div + 28
    draw_rounded_rect(draw, [PAD, y, W // 2 - 16, y + 140], 16, CARD_BG)
    draw.text((PAD + 20, y + 18), "ДОХОДЫ", font=f_label, fill=TEXT_MUTED)
    draw.text((PAD + 20, y + 44), f"+{total_income:,.2f} €", font=f_medium, fill=INCOME_COLOR)
    draw.text((PAD + 20, y + 84), f"💳  {income_card:,.2f} €", font=f_label, fill=TEXT_DARK)
    draw.text((PAD + 20, y + 110), f"💵  {income_cash:,.2f} €", font=f_label, fill=TEXT_DARK)

    # Expense block
    x2 = W // 2 + 16
    draw_rounded_rect(draw, [x2, y, W - PAD, y + 140], 16, CARD_BG)
    draw.text((x2 + 20, y + 18), "РАСХОДЫ", font=f_label, fill=TEXT_MUTED)
    draw.text((x2 + 20, y + 44), f"-{total_expense:,.2f} €", font=f_medium, fill=EXPENSE_COLOR)
    draw.text((x2 + 20, y + 84), f"💳  {expense_card:,.2f} €", font=f_label, fill=TEXT_DARK)
    draw.text((x2 + 20, y + 110), f"💵  {expense_cash:,.2f} €", font=f_label, fill=TEXT_DARK)

    # Divider
    y_div2 = y + 160
    draw.rectangle([PAD, y_div2, W - PAD, y_div2 + 1], fill=DIVIDER)

    # Card / Cash totals
    y3 = y_div2 + 24
    draw.text((PAD, y3), "💳  Карта", font=f_label, fill=TEXT_MUTED)
    card_balance = income_card - expense_card
    draw.text((PAD, y3 + 28), f"{'+' if card_balance >= 0 else ''}{card_balance:,.2f} €", font=f_medium,
              fill=INCOME_COLOR if card_balance >= 0 else EXPENSE_COLOR)

    draw.text((W // 2 + 16, y3), "💵  Наличные", font=f_label, fill=TEXT_MUTED)
    cash_balance = income_cash - expense_cash
    draw.text((W // 2 + 16, y3 + 28), f"{'+' if cash_balance >= 0 else ''}{cash_balance:,.2f} €", font=f_medium,
              fill=INCOME_COLOR if cash_balance >= 0 else EXPENSE_COLOR)

    # Footer
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    draw.text((PAD, H - 36), f"Обновлено {now}", font=f_label, fill=TEXT_MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG", quality=95)
    buf.seek(0)
    return buf
