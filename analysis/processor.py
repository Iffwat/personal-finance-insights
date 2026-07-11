import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# CATEGORIZATION RULES
#
# Rules are evaluated in ORDER — the FIRST match wins.
# Each rule is a dict with:
#   "keywords"       : list of lowercase substrings; ANY match triggers rule
#   "extra_require"  : (optional) list; at least ONE must ALSO be present
#   "category"       : the category label to assign
#   "type_override"  : (optional) overrides the Type determined by amount sign
#
# ---------------------------------------------------------------------------
# HOW TABUNG / FUND TRANSFERS WORK (Maybank & typical MY statements):
#
#  When you SEND money TO your tabung (e.g. Tabung Haji, ASB, PRS):
#    -> Amount is NEGATIVE in your bank statement (money leaves your account)
#    -> Description contains: "fund", "tabung", "amanah", etc.
#    -> Category : "Savings / Tabung"   |  Type override : "Savings Transfer"
#
#  When you WITHDRAW from your tabung back to your account:
#    -> Amount is POSITIVE (money enters your account)
#    -> Description contains: "wtdrw", "withdrawal", "pengeluaran" AND
#       also "fund", "tabung", or "amanah"
#    -> Category : "Tabung Withdrawal"  |  Type override : "Income"
#
#  EXAMPLE DESCRIPTIONS:
#    "TRANSFER FROM A/C MUHAMMAD IRSYAD IFF* 00000001 FUND Future"
#       -> matches "fund future" rule -> Savings / Tabung
#
#    "FUND TRANSFER TO A/ MUHAMMAD IRSYAD IFF* 00000001 WTDRW Future"
#       -> matches "wtdrw" + "fund" -> Tabung Withdrawal / Income
# ---------------------------------------------------------------------------

RULES = [
    # == TABUNG / FUND (must be checked BEFORE generic transfer rules) ========
    {
        "keywords": ["wtdrw", "withdrawal", "pengeluaran"],
        "extra_require": ["fund", "tabung", "amanah"],
        "category": "Tabung Withdrawal",
        "expected_sign": 1,
    },
    {
        "keywords": ["fund future", "tabung future", "iff*"],
        "category": "Savings / Tabung",
        "expected_sign": -1,
    },
    {
        "keywords": ["tabung haji"],
        "category": "Tabung Haji",
    },
    {
        "keywords": ["amanah saham", " asb ", "asnb", "kwsp", " epf ",
                     "prs ", "public mutual", "manulife", "principal asset"],
        "category": "Savings / Tabung",
        "expected_sign": -1,
    },

    # == SALARY / INCOME ======================================================
    {
        "keywords": ["salary", "gaji", "payroll", "emolumen", "allowance", "elaun",
                     "bonus", "dividen", "dividend", "hr payroll", "incentive"],
        "category": "Salary / Income",
        "expected_sign": 1,
    },

    # == INBOUND TRANSFERS (money received) ===================================
    {
        "keywords": ["transfer from", "transfer drpd", "penerimaan",
                     "received from", "masuk dari", "credit from",
                     "ibg cr", "duitnow cr", "interbank cr"],
        "category": "Transfer In",
        "expected_sign": 1,
    },

    # == OUTBOUND TRANSFERS ===================================================
    {
        "keywords": ["transfer to", "transfer ke", "hantar ke", "sent to",
                     "ibg dr", "duitnow dr", "interbank dr"],
        "category": "Bank Transfer Out",
        "expected_sign": -1,
    },

    # == DUITNOW / ONLINE BANKING =============================================
    {
        "keywords": ["duitnow", "jompay", "fpx", "online payment", "online banking",
                     "maybank2u", "m2u", "cimb clicks", "rhb now"],
        "category": "Online Payment",
    },

    # == LOAN / FINANCING =====================================================
    {
        "keywords": ["loan", "pinjaman", "mortgage", "rumah", "pembiayaan",
                     "hire purchase", "car loan", "kereta", "auto finance",
                     "housing loan", "mrta", "mlta"],
        "category": "Loan / Financing",
    },

    # == UTILITIES & BILLS ====================================================
    {
        "keywords": ["tnb ", "tenaga nasional", "syabas", "indah water", "air selangor",
                     "telekom", "unifi", "maxis", "celcom", "digi", "yes 4g",
                     "u mobile", "astro", "streamyx", "utility", "bil bayaran",
                     "bill payment", "sewerage"],
        "category": "Utilities & Bills",
    },

    # == INSURANCE / TAKAFUL ==================================================
    {
        "keywords": ["insurans", "insurance", "takaful", "great eastern", "allianz",
                     "prudential", "aia ", "etiqa", "zurich", "tokio marine"],
        "category": "Insurance / Takaful",
    },

    # == GOVERNMENT / TAX =====================================================
    {
        "keywords": ["lhdn", "hasil", "cukai", "zakat", "tax", "income tax",
                     "jpj", "road tax", "sst", "gst", "perkeso", "socso", "eis "],
        "category": "Tax & Government",
    },

    # == TRANSPORT ============================================================
    {
        "keywords": ["grab", "myrapid", "rapidkl", " lrt ", " mrt ", " ktm ",
                     "touch n go", " tng ", "e-wallet top", "petronas", "shell",
                     "petron", "caltex", "bpcm", "plus highway", "lebuhraya",
                     "parking", "uber", "lyft", " bas ", "transit", "grab car",
                     "maxim", "indriver", "hailo"],
        "category": "Transport",
    },

    # == FOOD & DINING ========================================================
    {
        "keywords": ["foodpanda", "grabfood", "grab food", "shopeefood",
                     "mcdonalds", "mcd ", "kfc", "pizza hut", "domino",
                     "tealive", "chatime", "zus coffee", "starbucks", "oldtown",
                     "secret recipe", "nandos", "marrybrown", "burger king",
                     "subway", "wendys", "restaurant", "restoran", "kedai makan",
                     "mamak", "cafe", "coffee", "bakery", "doordash",
                     "makan", "nasi lemak", "roti canai"],
        "category": "Food & Dining",
    },

    # == GROCERIES ============================================================
    {
        "keywords": ["mydin", "giant", "tesco", "aeon", "jaya grocer",
                     "99 speedmart", "99speedmart", "lotus", "cold storage",
                     "econsave", "village grocer", "walmart", "costco",
                     "supermarket", "pasar raya", "groceries", "pasaraya"],
        "category": "Groceries",
    },

    # == SHOPPING / E-COMMERCE ================================================
    {
        "keywords": ["shopee", "lazada", "zalora", "amazon", "taobao", "alibaba",
                     "h&m", "uniqlo", "parkson", "isetan", "sogo", "bonia",
                     "padini", "cotton on", "online shopping", "e-commerce",
                     "vivo ", "app store", "google play"],
        "category": "Shopping",
    },

    # == HEALTH & MEDICAL =====================================================
    {
        "keywords": ["hospital", "klinik", "clinic", "farmasi", "pharmacy",
                     "guardian", "watsons", "dental", "doktor", "doctor",
                     "ubat", "medicine", "medical", "optik", "optical"],
        "category": "Health & Medical",
    },

    # == EDUCATION ============================================================
    {
        "keywords": ["yuran", "fees", "tuition", "university", "kolej", "college",
                     "sekolah", "school", "ptptn", "scholarship", "bursary",
                     "pendidikan", "education"],
        "category": "Education",
    },

    # == ENTERTAINMENT & SUBSCRIPTIONS ========================================
    {
        "keywords": ["netflix", "spotify", "youtube", "disney", "hbo", "viu",
                     "iflix", "tonton", "apple music", "amazon prime",
                     "steam", "subscript", "membership"],
        "category": "Entertainment & Subscriptions",
    },

    # == ATM / CASH WITHDRAWAL ================================================
    {
        "keywords": ["atm withdrawal", "cash withdrawal", "pengeluaran tunai", "cdm"],
        "category": "Cash Withdrawal",
        "type_override": "Expense",
    },
]


def categorize_transaction(description: str, amount: float = 0.0):
    """
    Returns (category: str, type_override: str | None).
    type_override, if set, will replace the sign-based Type assignment.
    """
    if not description:
        return "Other", None

    desc_lower = str(description).lower().strip()

    for rule in RULES:
        keywords = rule.get("keywords", [])
        extra    = rule.get("extra_require", [])

        if not any(kw in desc_lower for kw in keywords):
            continue

        if extra and not any(ex in desc_lower for ex in extra):
            continue

        expected_sign = rule.get("expected_sign", 0)
        if expected_sign == 1 and amount < 0:
            continue
        if expected_sign == -1 and amount > 0:
            continue

        return rule["category"]

    return "Other"


def process_transactions(df: pd.DataFrame) -> pd.DataFrame:
    clean_df = df.copy()

    # 1. Parse amounts (handles RM, $, comma-separated, bracketed negatives)
    def parse_amount(val):
        if pd.isna(val) or val is None:
            return 0.0
        val_str = (str(val)
                   .replace("$", "")
                   .replace("RM", "")
                   .replace(",", "")
                   .strip())
        if val_str.startswith("(") and val_str.endswith(")"):
            val_str = "-" + val_str[1:-1]
        try:
            return float(val_str)
        except ValueError:
            return 0.0

    clean_df["Amount"] = clean_df["Amount"].apply(parse_amount)

    # 2. Base Type from amount sign
    clean_df["Type"] = np.where(clean_df["Amount"] >= 0, "Income", "Expense")

    # 3. Apply categorization
    def apply_categorization(row):
        cat = categorize_transaction(
            row.get("Description", ""), row.get("Amount", 0.0)
        )
        return cat

    clean_df["Category"] = clean_df.apply(apply_categorization, axis=1)

    return clean_df
