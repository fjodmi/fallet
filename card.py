from PIL import Image, ImageDraw, ImageFont
import io
import zoneinfo
from datetime import datetime

BG = "#E8E4DA"
INNER_CARD = "#D8D4CA"
TEXT_DARK = "#2C2C2C"
TEXT_MUTED = "#8C8780"
INCOME_COLOR = "#2D6A4F"
EXPENSE_COLOR = "#FF5A5A"
DIVIDER = "#CCC8BE"
DOT_COLOR = "#E05555"

GROTESK = "SpaceGrotesk-Regular.ttf"
GROTESK_BOLD = "SpaceGrotesk-Bold.ttf"
MONO = "SpaceMono-Regular.ttf"

def lf(path, size):
    try:
        return ImageFont.truetype(path, size)
    except:
        return ImageFont.load_default()

def rounded_rect(draw, xy, r, fill):
    x1, y1, x2, y2 = xy
    draw.rectangle([x1+r, y1, x2-r, y2], fill=fill)
    draw.rectangle([x1, y1+r, x2, y2-r], fill=fill)
    for cx, cy in [(x1,y1),(x2-2*r,y1),(x1,y2-2*r),(x2-2*r,y2-2*r)]:
        draw.ellipse([cx, cy, cx+2*r, cy+2*r], fill=fill)

def draw_logo(draw, f_logo, f_label, INNER_PAD, right_text):
    draw.text((INNER_PAD, 72), "FALLET", font=f_logo, fill=TEXT_DARK)
    logo_w = draw.textlength("FALLET", font=f_logo)
    dot_size = 14
    dot_x = INNER_PAD + logo_w + 5
    dot_y = 72 + 52 - dot_size - 4
    draw.ellipse([dot_x, dot_y, dot_x + dot_size, dot_y + dot_size], fill=DOT_COLOR)
    right_w = draw.textlength(right_text, font=f_label)
    draw.text((1080 - INNER_PAD - right_w, 88), right_text, font=f_label, fill=TEXT_MUTED)


def generate_balance_card(income_card, income_cash, expense_card, expense_cash, month_name):
    W, H = 1080, 920
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    total_income = income_card + income_cash
    total_expense = expense_card + expense_cash
    balance = total_income - total_expense
    balance_card = income_card - expense_card
    balance_cash = income_cash - expense_cash

    f_logo = lf(GROTESK_BOLD, 52)
    f_balance = lf(GROTESK_BOLD, 96)
    f_amount = lf(GROTESK_BOLD, 58)
    f_label = lf(MONO, 24)
    f_sub = lf(GROTESK, 30)
    f_muted = lf(GROTESK, 26)
    f_footer = lf(MONO, 20)
    f_section = lf(GROTESK_BOLD, 34)

    INNER_PAD = 72

    rounded_rect(draw, [32, 32, W-32, H-32], 40, "#E2DDD3")
    draw_logo(draw, f_logo, f_label, INNER_PAD, month_name.upper())

    y = 180
    draw.text((INNER_PAD, y), "Balance", font=f_muted, fill=TEXT_MUTED)
    y += 44
    balance_color = INCOME_COLOR if balance >= 0 else EXPENSE_COLOR
    balance_text = f"{'+' if balance >= 0 else ''}{balance:,.2f} €"
    draw.text((INNER_PAD, y), balance_text, font=f_balance, fill=balance_color)

    y += 124
    draw.rectangle([INNER_PAD, y, W-INNER_PAD, y+1], fill=DIVIDER)
    y += 32

    card_w = (W - INNER_PAD*2 - 24) // 2
    card_h = 270
    cx1, cx2 = INNER_PAD, INNER_PAD + card_w + 24
    cy = y

    rounded_rect(draw, [cx1, cy, cx1+card_w, cy+card_h], 20, INNER_CARD)
    draw.text((cx1+28, cy+24), "INCOME", font=f_label, fill=TEXT_MUTED)
    draw.text((cx1+28, cy+58), f"+{total_income:,.2f} €", font=f_amount, fill=INCOME_COLOR)
    draw.text((cx1+28, cy+143), "Card", font=f_label, fill=TEXT_MUTED)
    draw.text((cx1+28, cy+170), f"{income_card:,.2f} €", font=f_muted, fill=TEXT_DARK)
    draw.text((cx1+28, cy+200), "Cash", font=f_label, fill=TEXT_MUTED)
    draw.text((cx1+28, cy+227), f"{income_cash:,.2f} €", font=f_muted, fill=TEXT_DARK)

    rounded_rect(draw, [cx2, cy, cx2+card_w, cy+card_h], 20, INNER_CARD)
    draw.text((cx2+28, cy+24), "EXPENSES", font=f_label, fill=TEXT_MUTED)
    draw.text((cx2+28, cy+58), f"-{total_expense:,.2f} €", font=f_amount, fill=EXPENSE_COLOR)
    draw.text((cx2+28, cy+143), "Card", font=f_label, fill=TEXT_MUTED)
    draw.text((cx2+28, cy+170), f"{expense_card:,.2f} €", font=f_muted, fill=TEXT_DARK)
    draw.text((cx2+28, cy+200), "Cash", font=f_label, fill=TEXT_MUTED)
    draw.text((cx2+28, cy+227), f"{expense_cash:,.2f} €", font=f_muted, fill=TEXT_DARK)

    y2 = cy + card_h + 36
    draw.rectangle([INNER_PAD, y2, W-INNER_PAD, y2+1], fill=DIVIDER)
    y2 += 40

    mid = W // 2
    draw.text((INNER_PAD, y2), "Card", font=f_muted, fill=TEXT_MUTED)
    card_color = INCOME_COLOR if balance_card >= 0 else EXPENSE_COLOR
    draw.text((INNER_PAD, y2+40), f"{'+' if balance_card >= 0 else ''}{balance_card:,.2f} €", font=f_section, fill=card_color)

    draw.text((mid+4, y2), "Cash", font=f_muted, fill=TEXT_MUTED)
    cash_color = INCOME_COLOR if balance_cash >= 0 else EXPENSE_COLOR
    draw.text((mid+4, y2+40), f"{'+' if balance_cash >= 0 else ''}{balance_cash:,.2f} €", font=f_section, fill=cash_color)

    now = datetime.now(zoneinfo.ZoneInfo("Europe/Tallinn")).strftime("%d.%m.%Y %H:%M")
    draw.text((INNER_PAD, H-80), f"Updated {now}", font=f_footer, fill=TEXT_MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_breakdown_card(inc_by_cat, exp_by_cat, total_income, total_expense, month_name):
    W = 1080
    n_cats = len(inc_by_cat) + len(exp_by_cat)
    H = max(920, 400 + n_cats * 90)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    f_logo = lf(GROTESK_BOLD, 52)
    f_label = lf(MONO, 22)
    f_amount = lf(GROTESK_BOLD, 38)
    f_muted = lf(GROTESK, 26)
    f_footer = lf(MONO, 20)
    f_section = lf(GROTESK_BOLD, 28)

    INNER_PAD = 72
    BAR_W = W - INNER_PAD * 2

    rounded_rect(draw, [32, 32, W-32, H-32], 40, "#E2DDD3")
    draw_logo(draw, f_logo, f_label, INNER_PAD, month_name.upper())

    y = 172
    draw.rectangle([INNER_PAD, y, W-INNER_PAD, y+1], fill=DIVIDER)
    y += 32

    draw.text((INNER_PAD, y), "INCOME", font=f_label, fill=TEXT_MUTED)
    y += 36

    for cat, amt in sorted(inc_by_cat.items(), key=lambda x: -x[1]):
        pct = (amt / total_income * 100) if total_income else 0
        bar_fill = int(BAR_W * pct / 100)
        draw.text((INNER_PAD, y), cat, font=f_muted, fill=TEXT_DARK)
        amt_text = f"+{amt:,.2f} €"
        amt_w = draw.textlength(amt_text, font=f_section)
        draw.text((W - INNER_PAD - amt_w, y), amt_text, font=f_section, fill=INCOME_COLOR)
        y += 38
        rounded_rect(draw, [INNER_PAD, y, INNER_PAD + BAR_W, y + 14], 7, INNER_CARD)
        if bar_fill > 0:
            rounded_rect(draw, [INNER_PAD, y, INNER_PAD + bar_fill, y + 14], 7, INCOME_COLOR)
        pct_w = draw.textlength(f"{pct:.0f}%", font=f_label)
        draw.text((W - INNER_PAD - pct_w, y - 2), f"{pct:.0f}%", font=f_label, fill=TEXT_MUTED)
        y += 36

    y += 16
    draw.rectangle([INNER_PAD, y, W-INNER_PAD, y+1], fill=DIVIDER)
    y += 32

    draw.text((INNER_PAD, y), "EXPENSES", font=f_label, fill=TEXT_MUTED)
    y += 36

    for cat, amt in sorted(exp_by_cat.items(), key=lambda x: -x[1]):
        pct = (amt / total_expense * 100) if total_expense else 0
        bar_fill = int(BAR_W * pct / 100)
        draw.text((INNER_PAD, y), cat, font=f_muted, fill=TEXT_DARK)
        amt_text = f"-{amt:,.2f} €"
        amt_w = draw.textlength(amt_text, font=f_section)
        draw.text((W - INNER_PAD - amt_w, y), amt_text, font=f_section, fill=EXPENSE_COLOR)
        y += 38
        rounded_rect(draw, [INNER_PAD, y, INNER_PAD + BAR_W, y + 14], 7, INNER_CARD)
        if bar_fill > 0:
            rounded_rect(draw, [INNER_PAD, y, INNER_PAD + bar_fill, y + 14], 7, EXPENSE_COLOR)
        pct_w = draw.textlength(f"{pct:.0f}%", font=f_label)
        draw.text((W - INNER_PAD - pct_w, y - 2), f"{pct:.0f}%", font=f_label, fill=TEXT_MUTED)
        y += 36

    y += 24
    now = datetime.now(zoneinfo.ZoneInfo("Europe/Tallinn")).strftime("%d.%m.%Y %H:%M")
    draw.text((INNER_PAD, y), f"Updated {now}", font=f_footer, fill=TEXT_MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_compare_card(cur_inc, prev_inc, cur_exp, prev_exp, cur_month, prev_month):
    W = 1080
    n_cats = len(set(list(cur_inc.keys()) + list(prev_inc.keys()))) + len(set(list(cur_exp.keys()) + list(prev_exp.keys())))
    H = max(920, 420 + n_cats * 80)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    f_logo = lf(GROTESK_BOLD, 52)
    f_label = lf(MONO, 22)
    f_muted = lf(GROTESK, 26)
    f_amount = lf(GROTESK, 28)
    f_section = lf(GROTESK_BOLD, 30)
    f_total = lf(GROTESK_BOLD, 42)
    f_footer = lf(MONO, 20)

    INNER_PAD = 72
    COL1 = INNER_PAD
    COL2 = 420
    COL3 = 620
    COL4 = 820

    rounded_rect(draw, [32, 32, W-32, H-32], 40, "#E2DDD3")
    header = f"{prev_month.upper()} vs {cur_month.upper()}"
    draw_logo(draw, f_logo, f_label, INNER_PAD, header)

    y = 172
    draw.rectangle([INNER_PAD, y, W-INNER_PAD, y+1], fill=DIVIDER)
    y += 32

    draw.text((COL1, y), "CATEGORY", font=f_label, fill=TEXT_MUTED)
    prev_w = draw.textlength(prev_month.upper(), font=f_label)
    draw.text((COL2 + (160 - prev_w)//2, y), prev_month.upper(), font=f_label, fill=TEXT_MUTED)
    cur_w = draw.textlength(cur_month.upper(), font=f_label)
    draw.text((COL3 + (160 - cur_w)//2, y), cur_month.upper(), font=f_label, fill=TEXT_MUTED)
    draw.text((COL4, y), "CHANGE", font=f_label, fill=TEXT_MUTED)
    y += 36

    draw.rectangle([INNER_PAD, y, W-INNER_PAD, y+1], fill=DIVIDER)
    y += 24

    def draw_row(y, cat, prev, cur, is_income):
        delta = cur - prev
        if is_income:
            delta_color = INCOME_COLOR if delta >= 0 else EXPENSE_COLOR
        else:
            delta_color = EXPENSE_COLOR if delta >= 0 else INCOME_COLOR
        arrow = "↑" if delta >= 0 else "↓"
        draw.text((COL1, y), cat, font=f_muted, fill=TEXT_DARK)
        prev_text = f"{prev:,.0f} €"
        prev_w = draw.textlength(prev_text, font=f_amount)
        draw.text((COL2 + (160 - prev_w)//2, y), prev_text, font=f_amount, fill=TEXT_MUTED)
        cur_text = f"{cur:,.0f} €"
        cur_w = draw.textlength(cur_text, font=f_amount)
        draw.text((COL3 + (160 - cur_w)//2, y), cur_text, font=f_amount, fill=TEXT_DARK)
        delta_text = f"{arrow} {'+' if delta >= 0 else ''}{delta:,.0f}"
        draw.text((COL4, y), delta_text, font=f_section, fill=delta_color)
        return y + 56

    draw.text((COL1, y), "INCOME", font=f_label, fill=INCOME_COLOR)
    y += 36

    all_inc = set(list(cur_inc.keys()) + list(prev_inc.keys()))
    total_cur_inc = sum(cur_inc.values())
    total_prev_inc = sum(prev_inc.values())

    for cat in sorted(all_inc):
        y = draw_row(y, cat, prev_inc.get(cat, 0), cur_inc.get(cat, 0), True)

    draw.rectangle([INNER_PAD, y, W-INNER_PAD, y+1], fill=DIVIDER)
    y += 16
    delta_inc = total_cur_inc - total_prev_inc
    delta_color = INCOME_COLOR if delta_inc >= 0 else EXPENSE_COLOR
    arrow = "↑" if delta_inc >= 0 else "↓"
    draw.text((COL1, y), "Total", font=f_section, fill=TEXT_DARK)
    prev_w = draw.textlength(f"{total_prev_inc:,.0f} €", font=f_section)
    draw.text((COL2 + (160-prev_w)//2, y), f"{total_prev_inc:,.0f} €", font=f_section, fill=TEXT_MUTED)
    cur_w = draw.textlength(f"{total_cur_inc:,.0f} €", font=f_section)
    draw.text((COL3 + (160-cur_w)//2, y), f"{total_cur_inc:,.0f} €", font=f_section, fill=INCOME_COLOR)
    draw.text((COL4, y), f"{arrow} {'+' if delta_inc >= 0 else ''}{delta_inc:,.0f}", font=f_section, fill=delta_color)
    y += 56

    draw.rectangle([INNER_PAD, y, W-INNER_PAD, y+1], fill=DIVIDER)
    y += 24

    draw.text((COL1, y), "EXPENSES", font=f_label, fill=EXPENSE_COLOR)
    y += 36

    all_exp = set(list(cur_exp.keys()) + list(prev_exp.keys()))
    total_cur_exp = sum(cur_exp.values())
    total_prev_exp = sum(prev_exp.values())

    for cat in sorted(all_exp):
        y = draw_row(y, cat, prev_exp.get(cat, 0), cur_exp.get(cat, 0), False)

    draw.rectangle([INNER_PAD, y, W-INNER_PAD, y+1], fill=DIVIDER)
    y += 16
    delta_exp = total_cur_exp - total_prev_exp
    delta_color = EXPENSE_COLOR if delta_exp >= 0 else INCOME_COLOR
    arrow = "↑" if delta_exp >= 0 else "↓"
    draw.text((COL1, y), "Total", font=f_section, fill=TEXT_DARK)
    prev_w = draw.textlength(f"{total_prev_exp:,.0f} €", font=f_section)
    draw.text((COL2 + (160-prev_w)//2, y), f"{total_prev_exp:,.0f} €", font=f_section, fill=TEXT_MUTED)
    cur_w = draw.textlength(f"{total_cur_exp:,.0f} €", font=f_section)
    draw.text((COL3 + (160-cur_w)//2, y), f"{total_cur_exp:,.0f} €", font=f_section, fill=EXPENSE_COLOR)
    draw.text((COL4, y), f"{arrow} {'+' if delta_exp >= 0 else ''}{delta_exp:,.0f}", font=f_section, fill=delta_color)
    y += 60

    draw.rectangle([INNER_PAD, y, W-INNER_PAD, y+1], fill=DIVIDER)
    y += 24
    prev_bal = total_prev_inc - total_prev_exp
    cur_bal = total_cur_inc - total_cur_exp
    delta_bal = cur_bal - prev_bal
    bal_color = INCOME_COLOR if cur_bal >= 0 else EXPENSE_COLOR
    delta_color = INCOME_COLOR if delta_bal >= 0 else EXPENSE_COLOR
    arrow = "↑" if delta_bal >= 0 else "↓"
    draw.text((COL1, y), "BALANCE", font=f_label, fill=TEXT_MUTED)
    y += 32
    draw.text((COL1, y), f"{prev_bal:,.0f} €", font=f_total, fill=TEXT_MUTED)
    draw.text((COL3, y), f"{cur_bal:,.0f} €", font=f_total, fill=bal_color)
    draw.text((COL4, y), f"{arrow} {'+' if delta_bal >= 0 else ''}{delta_bal:,.0f}", font=f_section, fill=delta_color)
    y += 64

    now = datetime.now(zoneinfo.ZoneInfo("Europe/Tallinn")).strftime("%d.%m.%Y %H:%M")
    draw.text((INNER_PAD, y), f"Updated {now}", font=f_footer, fill=TEXT_MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
