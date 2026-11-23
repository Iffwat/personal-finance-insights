import unittest

import pandas as pd

from analysis.processor import process_transactions


class TransactionClassificationTests(unittest.TestCase):
    def classify(self, description, amount):
        result = process_transactions(pd.DataFrame([{
            "Date": "01/10/26",
            "Description": description,
            "Amount": amount,
        }]))
        return result.iloc[0]["Category"], result.iloc[0]["Type"]

    def test_future_tabung_deposit_is_internal(self):
        category, tx_type = self.classify(
            "TRANSFER FROM A/C MUHAMMAD IRSYAD IFF* 00000001 FUND Future",
            -200.00,
        )
        self.assertEqual(category, "Savings / Tabung")
        self.assertEqual(tx_type, "Internal Transfer")

    def test_future_tabung_withdrawal_is_not_income(self):
        category, tx_type = self.classify(
            "FUND TRANSFER TO A/ MUHAMMAD IRSYAD IFF* 00000001 WTDRW Future",
            73.95,
        )
        self.assertEqual(category, "Tabung Withdrawal")
        self.assertEqual(tx_type, "Internal Transfer")

    def test_booster_future_is_also_internal(self):
        category, tx_type = self.classify(
            "TRANSFER FROM A/C MUHAMMAD IRSYAD IFF* 00000001 BOOSTER Future",
            -0.50,
        )
        self.assertEqual(category, "Other Internal Transfer")
        self.assertEqual(tx_type, "Internal Transfer")

    def test_own_name_toll_allocation_is_not_expense(self):
        category, tx_type = self.classify(
            "IBK FUND TFR FR A/C MUHAMMAD IRSYAD IFF* Toll MBB CT",
            -12.00,
        )
        self.assertEqual(category, "Toll Allocation")
        self.assertEqual(tx_type, "Internal Transfer")

    def test_merchant_qr_payment_remains_an_expense(self):
        category, tx_type = self.classify(
            "IBK FUND TFR FR A/C NFA FOOD EMPIRE QR75797241 DUITNOW QR",
            -12.50,
        )
        self.assertEqual(category, "Food & Dining")
        self.assertEqual(tx_type, "Expense")

    def test_salary_and_reimbursement_are_separate(self):
        self.assertEqual(
            self.classify("ELVIRA SYSTEMS SDN. SALARY OCT 2026", 1751.70),
            ("Salary / Income", "Income"),
        )
        self.assertEqual(
            self.classify("ELVIRA SYSTEMS SDN. CLAIM 16102026", 1321.06),
            ("Expense Reimbursement", "Reimbursement"),
        )

    def test_person_transfer_is_not_automatically_income_or_expense(self):
        category, tx_type = self.classify(
            "IBK FUND TFR FR A/C JANE DOE QR123 DUITNOW QR",
            -50.00,
        )
        self.assertEqual(category, "Person-to-Person Transfer")
        self.assertEqual(tx_type, "External Transfer")


if __name__ == "__main__":
    unittest.main()
