from flask import Flask, jsonify, request
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
    rows = conn.execute(
        "SELECT * FROM transactions WHERE created_at LIKE ? ORDER BY created_at DESC",
        (f"{prefix}%",)
    ).fetchall()
    conn.close()

    income_card = sum(r["amount"] for r in rows if r["type"] == "income" and r["payment_method"] == "card")
    income_cash = sum(r["amount"] for r in rows if r["type"] == "income" and r["payment_method"] == "cash")
    expense_card = sum(r["amount"] for r in rows if r["type"] == "expense" and r["payment_method"] == "card")
    expense_cash = sum(r["amount"] for r in rows if r["type"] == "expense" and r["payment_method"] == "cash")

    return jsonify({
        "month": f"{year}-{int(month):02d}",
        "income": {"card": income_card, "cash": income_cash, "total": income_card + income_cash},
        "expense": {"card": expense_card, "cash": expense_cash, "total": expense_card + expense_cash},
        "balance": (income_card + income_cash) - (expense_card + expense_cash)
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
