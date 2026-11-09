import csv
import io
import json
import sqlite3
from datetime import datetime
from flask import Flask, Response, redirect, render_template, request, url_for

app = Flask(__name__)
DB_FILE = "budget.db"


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            budget REAL DEFAULT 3000.0
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '-',
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            note TEXT DEFAULT '-',
            created_at TEXT
        )
    """
    )

    cursor.execute("PRAGMA table_info(expenses)")
    columns = [column[1] for column in cursor.fetchall()]

    if "note" not in columns:
        try:
            cursor.execute(
                "ALTER TABLE expenses ADD COLUMN note TEXT DEFAULT '-'"
            )
        except Exception:
            pass

    if "title" not in columns:
        try:
            cursor.execute(
                "ALTER TABLE expenses ADD COLUMN title TEXT DEFAULT '-'"
            )
        except Exception:
            pass

    if "created_at" not in columns:
        try:
            cursor.execute("ALTER TABLE expenses ADD COLUMN created_at TEXT")
        except Exception:
            pass

    cursor.execute("SELECT COUNT(*) FROM settings")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO settings (id, budget) VALUES (1, 3000.0)")

    conn.commit()
    conn.close()


init_db()


@app.errorhandler(Exception)
def handle_exception(e):
    return redirect(url_for("index"))


@app.route("/", methods=["GET", "POST"])
def index():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        if "clear_all" in request.form:
            cursor.execute("DELETE FROM expenses")
            conn.commit()

        elif "expense_id" in request.form or "delete_expense" in request.form:
            expense_id = request.form.get("expense_id", type=int)
            if expense_id:
                cursor.execute(
                    "DELETE FROM expenses WHERE id = ?", (expense_id,)
                )
                conn.commit()

        elif (
            "update_budget" in request.form or "budget" in request.form
        ) and "category" not in request.form:
            new_budget = request.form.get("budget", type=float)
            if new_budget and new_budget > 0:
                cursor.execute(
                    "UPDATE settings SET budget = ? WHERE id = 1", (new_budget,)
                )
                conn.commit()

        elif "add_expense" in request.form or (
            "amount" in request.form and "category" in request.form
        ):
            amount = request.form.get("amount", type=float)
            category = request.form.get("category", "").strip()
            note = request.form.get("note", "").strip()

            if amount and category:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                val_note = note if note else "-"
                val_title = category

                cursor.execute("PRAGMA table_info(expenses)")
                columns = [col[1] for col in cursor.fetchall()]

                if "title" in columns and "note" in columns:
                    cursor.execute(
                        "INSERT INTO expenses (title, amount, category, note, created_at) VALUES (?, ?, ?, ?, ?)",
                        (val_title, amount, category, val_note, now_str),
                    )
                elif "title" in columns:
                    cursor.execute(
                        "INSERT INTO expenses (title, amount, category, created_at) VALUES (?, ?, ?, ?)",
                        (val_title, amount, category, now_str),
                    )
                elif "note" in columns:
                    cursor.execute(
                        "INSERT INTO expenses (amount, category, note, created_at) VALUES (?, ?, ?, ?)",
                        (amount, category, val_note, now_str),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO expenses (amount, category, created_at) VALUES (?, ?, ?)",
                        (amount, category, now_str),
                    )

                conn.commit()

        conn.close()
        return redirect(url_for("index"))

    cursor.execute("SELECT budget FROM settings LIMIT 1")
    row = cursor.fetchone()
    budget = row["budget"] if row else 3000.0

    cursor.execute("SELECT * FROM expenses ORDER BY id DESC")
    expenses = cursor.fetchall()

    total_spent = sum(item["amount"] for item in expenses)
    remaining = budget - total_spent

    if budget > 0:
        percentage = int(round((total_spent / budget) * 100))
    else:
        percentage = 0

    cat_map = {}
    for item in expenses:
        cat = item["category"]
        cat_map[cat] = cat_map.get(cat, 0) + item["amount"]

    categories = list(cat_map.keys())
    amounts = list(cat_map.values())

    conn.close()

    return render_template(
        "index.html",
        budget=budget,
        expenses=expenses,
        total_spent=total_spent,
        remaining=remaining,
        percentage=percentage,
        categories=categories,
        amounts=amounts,
    )


@app.route("/export/csv")
def export_csv():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(expenses)")
    columns = [col[1] for col in cursor.fetchall()]

    if "note" in columns:
        cursor.execute(
            "SELECT id, category, note, amount, created_at FROM expenses ORDER BY id DESC"
        )
    else:
        cursor.execute(
            "SELECT id, category, amount, created_at FROM expenses ORDER BY id DESC"
        )

    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(
        ["المعرف", "فئة الصرف", "الملاحظة", "المبلغ", "التاريخ والوقت"]
    )

    for r in rows:
        note_val = r["note"] if "note" in r.keys() else "-"
        writer.writerow(
            [r["id"], r["category"], note_val, r["amount"], r["created_at"]]
        )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=budget_expenses.csv"
        },
    )


@app.route("/export/json")
def export_json():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM expenses ORDER BY id DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return Response(
        json.dumps(rows, ensure_ascii=False, indent=4),
        mimetype="application/json",
        headers={
            "Content-Disposition": "attachment; filename=budget_expenses.json"
        },
    )


@app.route("/export/txt")
def export_txt():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT budget FROM settings LIMIT 1")
    budget = cursor.fetchone()["budget"]
    cursor.execute("SELECT * FROM expenses ORDER BY id DESC")
    expenses = cursor.fetchall()
    conn.close()

    total_spent = sum(e["amount"] for e in expenses)
    content = "=== تقرير الميزانية الشخصية ===\n"
    content += "فريق العمل: ماهر فريد علي شوايه | علي عالي مصلوف | حمد عبده كليب | عبدالله الريثي\n"
    content += "الجهة: الكلية التقنية بجازان\n"
    content += "-----------------------------------\n"
    content += f"الميزانية: {budget} ريال\nإجمالي المصروفات: {total_spent} ريال\nالمتبقي: {budget - total_spent} ريال\n\n"
    content += "--- تفاصيل المصروفات ---\n"

    for e in expenses:
        note_val = e["note"] if "note" in e.keys() else "-"
        content += f"[{e['created_at']}] {e['category']} - {note_val} - {e['amount']} ريال\n"

    return Response(
        content,
        mimetype="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=budget_report.txt"
        },
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)