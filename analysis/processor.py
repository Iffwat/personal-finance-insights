import pandas as pd
import numpy as np

# Ordered rules: merchant-specific rules are evaluated before generic bank
# transfers because QR merchant payments may also be labelled "IBK FUND TFR".
RULES = [
    {"keywords": ["wtdrw future", "wtdrw tabung"], "category": "Tabung Withdrawal", "type_override": "Internal Transfer"},
    {"keywords": ["fund future", "tabung future"], "category": "Savings / Tabung", "type_override": "Internal Transfer"},
    {"keywords": ["booster future"], "category": "Other Internal Transfer", "type_override": "Internal Transfer"},
    {"keywords": ["amanah saham", "asnb transfer", "asb transfer"], "category": "Investment / ASB", "type_override": "Investment"},
    {"keywords": ["salary", "gaji", "payroll", "emolumen", "allowance", "elaun", "bonus", "dividen", "dividend", "incentive"], "category": "Salary / Income", "type_override": "Income"},
    {"keywords": ["claim"], "category": "Expense Reimbursement", "type_override": "Reimbursement"},
    {"keywords": ["spotify", "apple.com/bill", "openai", "chatgpt", "netflix", "youtube", "disney", "hbo", "viu", "steam"], "category": "Subscriptions & Digital Services"},
    {"keywords": ["petronas", "shell", "petron", "caltex", "setel fuel"], "category": "Fuel"},
    {"keywords": ["plus-", "plus highway", "lebuhraya", "toll", "ldp", "kesas", "elite"], "category": "Toll & Parking"},
    {"keywords": ["grab-", "grab car", "myrapid", "rapidkl", "lrt", "mrt", "ktm", "parking", "maxim", "indriver"], "category": "Transport"},
    {"keywords": ["zus coffee", "foodpanda", "grabfood", "grab food", "mcdonald", "kfc", "pizza hut", "domino", "tealive", "starbucks", "restaurant", "restoran", "kedai makan", "mamak", "cafe", "coffee", "bakery", "ayam gepuk", "warong", "breakfast station", "food empire"], "category": "Food & Dining"},
    {"keywords": ["mydin", "giant", "tesco", "aeon", "jaya grocer", "99 speedmart", "lotus", "cold storage", "econsave", "village grocer", "supermarket", "pasar raya"], "category": "Groceries"},
    {"keywords": ["7-eleven", "7 eleven", "kk mart", "mynews", "99-mynews", "my news"], "category": "Convenience Stores"},
    {"keywords": ["shopee", "lazada", "zalora", "amazon", "taobao", "h&m", "uniqlo", "parkson", "sogo", "padini", "mr diy"], "category": "Shopping"},
    {"keywords": ["insurans", "insurance", "takaful", "great eastern", "allianz", "prudential", "aia ", "etiqa", "zurich"], "category": "Insurance / Takaful"},
    {"keywords": ["tnb", "tenaga nasional", "syabas", "indah water", "unifi", "maxis", "celcom", "digi", "astro", "utility", "bill payment"], "category": "Utilities & Bills"},
    {"keywords": ["barber", "salon"], "category": "Personal Care"},
    {"keywords": ["duit keta", "axia"], "category": "Vehicle Commitment"},
    {"keywords": ["duit berkat", "family"], "category": "Family Support"},
    {"keywords": ["atm withdrawal", "cash withdrawal", "pengeluaran tunai", "cdm"], "category": "Cash Withdrawal"},
    # Only generic/unidentified transfers reach this rule. Known merchant QR
    # payments have already been classified above.
    {"keywords": ["transfer to", "transfer from", "transfer drpd", "ibk fund tfr", "duitnow qr", "mae qr", "fund transfer"], "category": "Person-to-Person Transfer", "type_override": "External Transfer"},
]

def categorize_transaction(description: str, amount: float = 0.0):
    """Return (category, type override); internal transfers are not income/expense."""
    desc = str(description or "").lower().strip()
    for rule in RULES:
        if any(keyword in desc for keyword in rule["keywords"]):
            return rule["category"], rule.get("type_override")
    return "Other", None

def process_transactions(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.copy()

    def parse_amount(value):
        if pd.isna(value) or value is None:
            return 0.0
        text = str(value).replace("$", "").replace("RM", "").replace(",", "").strip()
        if text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1]
        try:
            return float(text)
        except (TypeError, ValueError):
            return 0.0

    clean["Amount"] = clean["Amount"].apply(parse_amount)
    categories, types = [], []
    for _, row in clean.iterrows():
        category, override = categorize_transaction(row.get("Description", ""), row["Amount"])
        categories.append(category)
        types.append(override or ("Income" if row["Amount"] >= 0 else "Expense"))
    clean["Category"] = categories
    clean["Type"] = types
    return clean
