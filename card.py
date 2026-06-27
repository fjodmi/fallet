from PIL import Image, ImageDraw, ImageFont
import io
from datetime import datetime

# Colors
BG = "#E8E4DA"
CARD_BG = "#DEDAB0"  # will override below
INNER_CARD = "#D8D4CA"
TEXT_DARK = "#2C2C2C"
TEXT_MUTED = "#8C8780"
INCOME_COLOR = "#2D6A4F"
EXPENSE_COLOR = "#E05555"
DIVIDER = "#CCC8BE"
DOT_COLOR = "#E05555"
CARD_SHADOW = "#CECA C0"

GROTESK = "SpaceGrotesk-Regular.ttf"
GROTESK_BOLD = "SpaceGrotesk-Bold.ttf"
MONO = "SpaceMono-Regular.ttf"

def lf(path, size):
    try:
        return ImageFont.truetype(path, size)
    except:
        try:
            return ImageFont.truetype(GROTESK, size)
        except:
            return ImageFont.load_default()

def rounded_rect(draw, xy, r, fill):
    x1, y1, x2, y2 = xy
    draw.rectangle([x1+r, y1, x2-r, y2], fill=fill)
    draw.rectangle([x1, y1+r, x2, y2-r], fill=fill)
    for cx, cy in [(x1,y1),(x2-2*r,y1),(x1,y2-2*r),(x2-2*r,y2-2*r)]:
        draw.ellipse([cx, cy, cx+2*r, cy+2*r], fill=fill)

def card_icon(draw, x, y, color):
    """Draw a simple card icon"""
    draw.rectangle([x, y+2, x+18, y+13], fill=color, outline=None)
    draw.rectangle([x, y+5, x+18, y+8], fill=BG)

def coin_icon(draw, x, y, color):
    """Draw a simple coin icon"""
    draw.ellipse([x, y, x+14, y+14], outline=color, width=2)

def generate_balance_card(income_card, income_cash, expense_card, expense_cash, month_name):
    W, H = 1080, 920
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    total_income = income_card + income_cash
    total_expense = expense_card + expense_cash
    balance = total_income - total_expense
    balance_card = income_card - expense_card
    balance_cash = income_cash - expense_cash

    # Fonts
    f_logo = lf(GROTESK_BOLD, 52)
    f_balance = lf(GROTESK_BOLD, 96)
    f_amount = lf(GROTESK_BOLD, 58)
    f_label = lf(MONO, 24)
    f_sub = lf(GROTESK, 30)
    f_muted = lf(GROTESK, 26)
    f_footer = lf(MONO, 20)
    f_section = lf(GROTESK_BOLD, 34)

    PAD = 72
    INNER_PAD = 72

    # Outer card with rounded corners
    rounded_rect(draw, [32, 32, W-32, H-32], 40, "#E2DDD3")

    # --- HEADER ---
    # Logo FALLET.
    draw.text((INNER_PAD, 72), "FALLET", font=f_logo, fill=TEXT_DARK)
    logo_w = draw.textlength("FALLET", font=f_logo)
    dot_size = 14
    dot_x = INNER_PAD + logo_w + 5
    dot_y = 72 + 52 - dot_size - 4
    draw.ellipse([dot_x, dot_y, dot_x + dot_size, dot_y + dot_size], fill=DOT_COLOR)

    # Month top right
    month_upper = month_name.upper()
    month_w = draw.textlength(month_upper, font=f_label)
    draw.text((W - INNER_PAD - month_w, 88), month_upper, font=f_label, fill=TEXT_MUTED)

    # --- BALANCE ---
    y = 180
    draw.text((INNER_PAD, y), "Balance", font=f_muted, fill=TEXT_MUTED)
    y += 44
    balance_color = INCOME_COLOR if balance >= 0 else EXPENSE_COLOR
    balance_text = f"{'+' if balance >= 0 else ''}{balance:,.2f} €"
    draw.text((INNER_PAD, y), balance_text, font=f_balance, fill=balance_color)

    # Divider
    y += 124
    draw.rectangle([INNER_PAD, y, W-INNER_PAD, y+1], fill=DIVIDER)
    y += 32

    # --- INCOME / EXPENSE CARDS ---
    card_w = (W - INNER_PAD*2 - 24) // 2
    card_h = 240
    cx1, cx2 = INNER_PAD, INNER_PAD + card_w + 24
    cy = y

    # Income card
    rounded_rect(draw, [cx1, cy, cx1+card_w, cy+card_h], 20, INNER_CARD)
    draw.text((cx1+28, cy+24), "INCOME", font=f_label, fill=TEXT_MUTED)
    draw.text((cx1+28, cy+58), f"+{total_income:,.2f} €", font=f_amount, fill=INCOME_COLOR)
    # Card icon + amount
    card_icon(draw, cx1+28, cy+148, TEXT_MUTED)
    draw.text((cx1+54, cy+143), f"{income_card:,.2f} €", font=f_muted, fill=TEXT_DARK)
    # Coin icon + amount
    coin_icon(draw, cx1+28, cy+186, TEXT_MUTED)
    draw.text((cx1+54, cy+183), f"{income_cash:,.2f} €", font=f_muted, fill=TEXT_DARK)

    # Expense card
    rounded_rect(draw, [cx2, cy, cx2+card_w, cy+card_h], 20, INNER_CARD)
    draw.text((cx2+28, cy+24), "EXPENSES", font=f_label, fill=TEXT_MUTED)
    draw.text((cx2+28, cy+58), f"-{total_expense:,.2f} €", font=f_amount, fill=EXPENSE_COLOR)
    card_icon(draw, cx2+28, cy+148, TEXT_MUTED)
    draw.text((cx2+54, cy+143), f"{expense_card:,.2f} €", font=f_muted, fill=TEXT_DARK)
    coin_icon(draw, cx2+28, cy+186, TEXT_MUTED)
    draw.text((cx2+54, cy+183), f"{expense_cash:,.2f} €", font=f_muted, fill=TEXT_DARK)

    # Divider 2
    y2 = cy + card_h + 36
    draw.rectangle([INNER_PAD, y2, W-INNER_PAD, y2+1], fill=DIVIDER)
    y2 += 40

    # --- CARD / CASH TOTALS ---
    mid = W // 2

    card_icon(draw, INNER_PAD, y2+6, TEXT_MUTED)
    draw.text((INNER_PAD+28, y2), "Card", font=f_muted, fill=TEXT_MUTED)
    card_color = INCOME_COLOR if balance_card >= 0 else EXPENSE_COLOR
    draw.text((INNER_PAD, y2+40), f"{'+' if balance_card >= 0 else ''}{balance_card:,.2f} €", font=f_section, fill=card_color)

    coin_icon(draw, mid+4, y2+6, TEXT_MUTED)
    draw.text((mid+26, y2), "Cash", font=f_muted, fill=TEXT_MUTED)
    cash_color = INCOME_COLOR if balance_cash >= 0 else EXPENSE_COLOR
    draw.text((mid+4, y2+40), f"{'+' if balance_cash >= 0 else ''}{balance_cash:,.2f} €", font=f_section, fill=cash_color)

    # Footer
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    draw.text((INNER_PAD, H-80), f"Updated {now}", font=f_footer, fill=TEXT_MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
