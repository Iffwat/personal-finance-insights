# 💹 Personal Finance Insights (Bank Statement Analyzer)

A powerful, interactive web application built with **Streamlit** to automatically parse, analyze, and visualize your financial transactions directly from PDF bank statements.

---

## ✨ Features

- **Automated PDF Parsing**: Extract transactions effortlessly from supported bank statements (currently supports **Maybank** and Generic formats) using `pdfplumber`.
- **Interactive Dashboards**: Deep dive into your spending and income trends with rich, dynamic charts powered by **Plotly**.
- **Financial KPIs**: Quickly understand your financial health at a glance with top-level key performance indicators (Total Income, Total Expenses, Net Savings, etc.).
- **Local SQLite Storage**: Your data stays yours. Parsed transactions are securely stored locally in an SQLite database, allowing you to build historical trends across multiple statements without cloud privacy concerns.
- **Dark Mode UI**: Beautifully crafted dark-themed interface for an optimal and modern user experience.

## 🛠️ Tech Stack

- **Frontend / Framework:** [Streamlit](https://streamlit.io/)
- **Data Manipulation:** [Pandas](https://pandas.pydata.org/), NumPy
- **Visualization:** [Plotly Express & Graph Objects](https://plotly.com/python/)
- **PDF Extraction:** [pdfplumber](https://github.com/jsvine/pdfplumber)
- **Database:** SQLite3

## 🚀 Getting Started

### Prerequisites
Make sure you have Python 3.8+ installed on your machine.

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Iffwat/personal-finance-insights.git
   cd personal-finance-insights
   ```

2. **Create a virtual environment (optional but recommended)**
   ```bash
   python -m venv venv
   # On Windows
   venv\Scripts\activate
   # On macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

### Running the App

Start the Streamlit server with the following command:
```bash
streamlit run app.py
```
The application will open automatically in your default web browser (usually at `http://localhost:8501`).

## 📖 Usage

1. **Import Statements**: Navigate to the sidebar, select **"Import New Statement"**, choose the corresponding bank format, and upload your PDF bank statements.
2. **Review Data**: The app will extract your transactions and securely store them in the local database.
3. **Analyze**: Switch to **"Load from History"** to explore interactive charts, track your spending categories, and gain actionable financial insights!

## 🔒 Privacy & Security
This application runs entirely locally. Your bank statements and financial data are never transmitted over the internet or sent to external servers. Data is kept locally within the `storage/` and `data/` directories, which are specifically git-ignored to prevent accidental uploads.

## 🤝 Contributing
Contributions, issues, and feature requests are welcome! Feel free to check the issues page.

---
*Built to make personal finance tracking a little less tedious and a lot more insightful.*


## Accounting model

The analyzer separates transaction direction from the financial meaning of a transaction:

- **Income**: salary and other earned income.
- **Reimbursements**: claim repayments are shown separately and are not treated as salary.
- **Actual expenses**: purchases, bills and merchant payments.
- **Internal transfers**: movements between accounts owned by the user. Transfers labelled `FUND Future` / `WTDRW Future` are recognised as deposits to and withdrawals from the Future (Tabung) holding account. These are excluded from income and expenses.
- **Other own-account allocations**: own-name transfers with memos such as Toll, Insurance or Game are shown separately from purchases.
- **Investments**: ASB/ASNB allocations are tracked separately from living expenses.
- **External transfers**: unidentified person-to-person transfers are shown separately until the user can verify their purpose.

The Cash Flow Map reconciles both the main-account movement and the overall surplus across owned accounts. Monthly and weekly views show net Future/Tabung movement (deposits less withdrawals), rather than treating every deposit as permanent savings. Historical transactions are reclassified with the current rules when loaded, so an existing local database does not need to be deleted or re-imported.

Classification is rule-based. Unidentified transfers and ambiguous merchants should be reviewed before relying on category totals.
