from flask import Flask, jsonify, request, send_file
import sqlite3
from datetime import datetime
from functools import wraps
import os

app = Flask(__name__)

DB_PATH = "/data/budget.db"
API_SECRET = os.getenv("API_SECRET", "fallet_secret")

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-API-Key") or request.args.get("key")
        if token != API_SECRET:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/api/summary")
@require_auth
def summary():
    year = request.args.get("year", datetime.now().year)
    month = request.args.get("month", datetime.now().month)
    prefix = f"{year}-{int(month):02d}"
    conn = get_db()

    # Current month income/expenses
    rows = conn.execute(
        "SELECT * FROM transactions WHERE created_at LIKE ? ORDER BY created_at DESC",
        (f"{prefix}%",)
    ).fetchall()

    # All-time transactions for balance
    all_rows = conn.execute(
        "SELECT * FROM transactions ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    income_card = sum(r["amount"] for r in rows if r["type"] == "income" and r["payment_method"] == "card")
    income_cash = sum(r["amount"] for r in rows if r["type"] == "income" and r["payment_method"] == "cash")
    expense_card = sum(r["amount"] for r in rows if r["type"] == "expense" and r["payment_method"] == "card")
    expense_cash = sum(r["amount"] for r in rows if r["type"] == "expense" and r["payment_method"] == "cash")

    # All-time balance
    all_income_card = sum(r["amount"] for r in all_rows if r["type"] == "income" and r["payment_method"] == "card")
    all_income_cash = sum(r["amount"] for r in all_rows if r["type"] == "income" and r["payment_method"] == "cash")
    all_expense_card = sum(r["amount"] for r in all_rows if r["type"] == "expense" and r["payment_method"] == "card")
    all_expense_cash = sum(r["amount"] for r in all_rows if r["type"] == "expense" and r["payment_method"] == "cash")

    balance_card = all_income_card - all_expense_card
    balance_cash = all_income_cash - all_expense_cash
    balance_total = balance_card + balance_cash

    return jsonify({
        "month": f"{year}-{int(month):02d}",
        "income": {"card": income_card, "cash": income_cash, "total": income_card + income_cash},
        "expense": {"card": expense_card, "cash": expense_cash, "total": expense_card + expense_cash},
        "balance": balance_total,
        "balance_card": balance_card,
        "balance_cash": balance_cash,
    })

@app.route("/api/transactions")
@require_auth
def transactions():
    year = request.args.get("year", datetime.now().year)
    month = request.args.get("month", datetime.now().month)
    prefix = f"{year}-{int(month):02d}"
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM transactions WHERE created_at LIKE ? ORDER BY created_at DESC",
        (f"{prefix}%",)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/breakdown")
@require_auth
def breakdown():
    year = request.args.get("year", datetime.now().year)
    month = request.args.get("month", datetime.now().month)
    prefix = f"{year}-{int(month):02d}"
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM transactions WHERE created_at LIKE ? ORDER BY created_at DESC",
        (f"{prefix}%",)
    ).fetchall()
    conn.close()
    exp_by_cat = {}
    inc_by_cat = {}
    for r in rows:
        if r["type"] == "expense":
            exp_by_cat[r["category"]] = exp_by_cat.get(r["category"], 0) + r["amount"]
        else:
            inc_by_cat[r["category"]] = inc_by_cat.get(r["category"], 0) + r["amount"]
    return jsonify({"income": inc_by_cat, "expense": exp_by_cat})

@app.route("/api/months")
@require_auth
def months():
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT substr(created_at, 1, 7) as month FROM transactions ORDER BY month DESC"
    ).fetchall()
    conn.close()
    return jsonify([r["month"] for r in rows])

@app.route("/api/compare")
@require_auth
def compare():
    now = datetime.now()
    cur_year = int(request.args.get("year", now.year))
    cur_month = int(request.args.get("month", now.month))
    prev_month = cur_month - 1 if cur_month > 1 else 12
    prev_year = cur_year if cur_month > 1 else cur_year - 1

    def get_data(y, m):
        prefix = f"{y}-{m:02d}"
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM transactions WHERE created_at LIKE ?", (f"{prefix}%",)
        ).fetchall()
        conn.close()
        inc = sum(r["amount"] for r in rows if r["type"] == "income")
        exp = sum(r["amount"] for r in rows if r["type"] == "expense")
        inc_by_cat = {}
        exp_by_cat = {}
        for r in rows:
            if r["type"] == "income":
                inc_by_cat[r["category"]] = inc_by_cat.get(r["category"], 0) + r["amount"]
            else:
                exp_by_cat[r["category"]] = exp_by_cat.get(r["category"], 0) + r["amount"]
        return {"income": inc, "expense": exp, "income_by_cat": inc_by_cat, "expense_by_cat": exp_by_cat}

    cur = get_data(cur_year, cur_month)
    prev = get_data(prev_year, prev_month)
    return jsonify({
        "current": {"month": f"{cur_year}-{cur_month:02d}", **cur},
        "previous": {"month": f"{prev_year}-{prev_month:02d}", **prev}
    })

@app.route("/api/transactions", methods=["POST"])
@require_auth
def add_transaction():
    data = request.get_json()
    required = ["type", "category", "amount", "payment_method"]
    for f in required:
        if f not in data:
            return jsonify({"error": f"Missing field: {f}"}), 400
    conn = get_db()
    conn.execute(
        "INSERT INTO transactions (type, category, amount, payment_method, comment, created_at) VALUES (?,?,?,?,?,?)",
        (data["type"], data["category"], float(data["amount"]),
         data["payment_method"], data.get("comment"), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/transactions/<int:tx_id>", methods=["PUT"])
@require_auth
def update_transaction(tx_id):
    data = request.get_json()
    allowed = ["type", "category", "amount", "payment_method", "comment"]
    conn = get_db()
    for field in allowed:
        if field in data:
            val = float(data[field]) if field == "amount" else data[field]
            conn.execute(f"UPDATE transactions SET {field}=? WHERE id=?", (val, tx_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/transactions/<int:tx_id>", methods=["DELETE"])
@require_auth
def delete_transaction(tx_id):
    conn = get_db()
    conn.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/miniapp.html")
def miniapp():
    return send_file("miniapp.html")

@app.route("/FALLET-wordmark-light.png")
def logo():
    return send_file("FALLET-wordmark-light.png")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
