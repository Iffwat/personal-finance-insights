import tempfile
import unittest
from pathlib import Path

import pandas as pd

from storage import database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        self.original_data_dir = database.DATA_DIR
        database.DATA_DIR = Path(self.temp_dir.name)
        database.DB_PATH = database.DATA_DIR / "test.sqlite3"
        database.init_db()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        database.DATA_DIR = self.original_data_dir
        self.temp_dir.cleanup()

    def test_statement_round_trip_and_delete(self):
        transactions = pd.DataFrame([
            {
                "Date": "01/10/26",
                "Description": "TRANSFER FROM A/C FUND Future",
                "Amount": -100.0,
                "Category": "Savings / Tabung",
                "Type": "Internal Transfer",
            },
            {
                "Date": "02/10/26",
                "Description": "ZUS COFFEE",
                "Amount": -15.0,
                "Category": "Food & Dining",
                "Type": "Expense",
            },
        ])

        count = database.save_transactions(
            transactions, "october.pdf::2026-10", 10, 2026
        )
        self.assertEqual(count, 2)
        self.assertTrue(database.statement_exists("october.pdf::2026-10"))

        loaded = database.load_transactions()
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded.iloc[0]["month"], 10)
        self.assertEqual(loaded.iloc[0]["year"], 2026)
        self.assertEqual(loaded.iloc[0]["Category"], "Savings / Tabung")

        statements = database.list_statements()
        self.assertEqual(len(statements), 1)
        self.assertEqual(int(statements.iloc[0]["num_rows"]), 2)
        self.assertEqual(database.get_db_stats(), (2, 1))

        database.delete_statement("october.pdf::2026-10")
        self.assertFalse(database.statement_exists("october.pdf::2026-10"))
        self.assertTrue(database.load_transactions().empty)
        self.assertEqual(database.get_db_stats(), (0, 0))

    def test_budget_upsert(self):
        database.save_budget("Food & Dining", 400)
        database.save_budget("Food & Dining", 450)
        self.assertEqual(database.load_budgets(), {"Food & Dining": 450.0})


if __name__ == "__main__":
    unittest.main()
