"""Local SQLite persistence for Personal Finance Insights.

The database lives under the ignored data/ directory. Only application code is
committed; bank statements and transaction records remain local to the user.
"""
from pathlib import Path
import sqlite3
from contextlib import contextmanager

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = DATA_DIR / "finance.sqlite3"


@contextmanager
def _connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DB_PATH), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    """Create the local database schema when the application first starts."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS statements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL UNIQUE,
                month INTEGER NOT NULL,
                year INTEGER NOT NULL,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                statement_id INTEGER NOT NULL,
                transaction_date TEXT,
                description TEXT NOT NULL DEFAULT '',
                amount REAL NOT NULL DEFAULT 0,
                balance REAL,
                category TEXT NOT NULL DEFAULT 'Other',
                type TEXT NOT NULL DEFAULT 'Expense',
                FOREIGN KEY (statement_id) REFERENCES statements(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_statement
                ON transactions(statement_id);
            CREATE INDEX IF NOT EXISTS idx_transactions_date
                ON transactions(transaction_date);

            CREATE TABLE IF NOT EXISTS budgets (
                category TEXT PRIMARY KEY,
                amount REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def statement_exists(filename):
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM statements WHERE filename = ? LIMIT 1",
            (str(filename),),
        ).fetchone()
    return row is not None


def save_transactions(df, filename, month, year):
    """Save parsed statement rows and return the number of stored transactions."""
    if df is None or df.empty:
        return 0

    required = {"Date", "Description", "Amount"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(
            "Transaction data is missing required columns: "
            + ", ".join(sorted(missing))
        )

    init_db()
    rows = []
    for _, row in df.iterrows():
        date_value = row.get("Date")
        if pd.isna(date_value):
            date_value = None
        else:
            date_value = str(date_value)

        amount_value = pd.to_numeric(row.get("Amount"), errors="coerce")
        if pd.isna(amount_value):
            amount_value = 0.0

        balance_value = pd.to_numeric(row.get("Balance"), errors="coerce")
        if pd.isna(balance_value):
            balance_value = None

        rows.append((
            date_value,
            str(row.get("Description", "") or ""),
            float(amount_value),
            None if balance_value is None else float(balance_value),
            str(row.get("Category", "Other") or "Other"),
            str(row.get("Type", "Expense") or "Expense"),
        ))

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO statements (filename, month, year)
            VALUES (?, ?, ?)
            ON CONFLICT(filename) DO UPDATE SET
                month = excluded.month,
                year = excluded.year
            """,
            (str(filename), int(month), int(year)),
        )
        statement = conn.execute(
            "SELECT id FROM statements WHERE filename = ?",
            (str(filename),),
        ).fetchone()
        statement_id = int(statement["id"])
        # Re-importing a statement replaces its transactions rather than
        # duplicating rows.
        conn.execute(
            "DELETE FROM transactions WHERE statement_id = ?",
            (statement_id,),
        )
        conn.executemany(
            """
            INSERT INTO transactions (
                statement_id, transaction_date, description, amount,
                balance, category, type
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [(statement_id, *row) for row in rows],
        )

    return len(rows)


def load_transactions():
    """Return all stored transactions with the columns expected by the app."""
    init_db()
    with _connect() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                t.transaction_date AS Date,
                t.description AS Description,
                t.amount AS Amount,
                t.balance AS Balance,
                t.category AS Category,
                t.type AS Type,
                s.month AS month,
                s.year AS year,
                s.filename AS filename
            FROM transactions AS t
            INNER JOIN statements AS s ON s.id = t.statement_id
            ORDER BY t.transaction_date, t.id
            """,
            conn,
        )
    if not df.empty:
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
        df["month"] = pd.to_numeric(df["month"], errors="coerce").astype("Int64")
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    return df


def list_statements():
    """Return imported statement metadata for the sidebar manager."""
    init_db()
    with _connect() as conn:
        return pd.read_sql_query(
            """
            SELECT
                s.filename,
                s.month,
                s.year,
                COUNT(t.id) AS num_rows
            FROM statements AS s
            LEFT JOIN transactions AS t ON t.statement_id = s.id
            GROUP BY s.id, s.filename, s.month, s.year
            ORDER BY s.year DESC, s.month DESC, s.filename
            """,
            conn,
        )


def delete_statement(filename):
    """Delete one statement and its transactions, without touching other data."""
    init_db()
    with _connect() as conn:
        conn.execute(
            "DELETE FROM statements WHERE filename = ?",
            (str(filename),),
        )


def get_db_stats():
    """Return (transaction_count, statement_count)."""
    init_db()
    with _connect() as conn:
        transaction_count = conn.execute(
            "SELECT COUNT(*) FROM transactions"
        ).fetchone()[0]
        statement_count = conn.execute(
            "SELECT COUNT(*) FROM statements"
        ).fetchone()[0]
    return int(transaction_count), int(statement_count)


def load_budgets():
    """Return budget targets as {category: amount}."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT category, amount FROM budgets ORDER BY category"
        ).fetchall()
    return {row["category"]: float(row["amount"]) for row in rows}


def save_budget(category, amount):
    """Insert or update one spending target."""
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO budgets (category, amount, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(category) DO UPDATE SET
                amount = excluded.amount,
                updated_at = CURRENT_TIMESTAMP
            """,
            (str(category), float(amount)),
        )
