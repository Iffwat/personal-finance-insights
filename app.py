import streamlit as st
import pandas as pd
import numpy as np
import os
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import datetime as _dt
import calendar as _cal

from parsers.generic_bank import GenericBankParser
from analysis.processor import process_transactions
from storage.database import (
    init_db, statement_exists, save_transactions,
    load_transactions, list_statements, delete_statement, get_db_stats,
)

# Initialise SQLite DB (creates tables on first run)
init_db()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Bank Statement Analyzer",
    layout="wide",
    page_icon="💹",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

  /* KPI Cards */
  .kpi-grid { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
  .kpi-card {
      flex: 1; min-width: 145px;
      background: linear-gradient(135deg, #1e2130 0%, #252b3b 100%);
      border-radius: 16px; padding: 1.1rem 1.3rem;
      border: 1px solid rgba(255,255,255,0.07);
      box-shadow: 0 4px 24px rgba(0,0,0,0.35);
      transition: transform .2s, box-shadow .2s;
  }
  .kpi-card:hover { transform: translateY(-4px); box-shadow: 0 8px 32px rgba(0,0,0,0.5); }
  .kpi-icon  { font-size: 1.3rem; margin-bottom: .35rem; }
  .kpi-label { font-size: .72rem; color: #8899aa; letter-spacing: .08em;
               text-transform: uppercase; margin-bottom: .2rem; }
  .kpi-value { font-size: 1.5rem; font-weight: 700; color: #ffffff; }
  .kpi-sub   { font-size: .76rem; margin-top: .25rem; }
  .positive  { color: #00e396; }
  .negative  { color: #ff4560; }
  .neutral   { color: #775dd0; }
  .savings   { color: #00b4d8; }

  /* Section headers */
  .section-header {
      font-size: 1.0rem; font-weight: 600; color: #c8d6e5;
      border-left: 3px solid #00e396; padding-left: .6rem;
      margin: 1.4rem 0 .7rem;
  }
  .section-header-week {
      font-size: 1.0rem; font-weight: 600; color: #c8d6e5;
      border-left: 3px solid #feb019; padding-left: .6rem;
      margin: 1.4rem 0 .7rem;
  }

  /* Divider */
  .fancy-divider {
      height: 1px;
      background: linear-gradient(to right, transparent,
                  rgba(255,255,255,0.12), transparent);
      margin: 1.4rem 0;
  }

  /* Filter badge */
  .filter-badge {
      display: inline-block; padding: .25rem .7rem;
      background: rgba(119,93,208,0.2); border: 1px solid #775dd0;
      border-radius: 20px; font-size: .78rem; color: #c8d6e5;
      margin: .15rem;
  }
</style>
""", unsafe_allow_html=True)

# ── Plotly dark layout ────────────────────────────────────────────────────────
DARK = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter", color="#c8d6e5"),
    margin=dict(t=50, l=10, r=10, b=10),
)
PAL = ["#00e396", "#775dd0", "#feb019", "#ff4560",
       "#008ffb", "#00cec9", "#e17055", "#74b9ff"]

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="padding:1rem 0 .4rem;">
  <h1 style="font-size:2.1rem;font-weight:700;margin:0;">Bank Statement Analyzer</h1>
  <p style="color:#8899aa;margin:.3rem 0 0;">
    Upload your PDF bank statements for rich financial insights.
  </p>
</div>
""", unsafe_allow_html=True)
st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)

# ── Sidebar — Mode + Import + Statement Manager ──────────────────────────────
with st.sidebar:
    st.markdown("### Mode")
    mode = st.radio(
        "Data source",
        ["Load from History", "Import New Statement"],
        label_visibility="collapsed",
    )
    st.markdown("---")

    if mode == "Import New Statement":
        st.markdown("### Import Settings")
        debug_mode  = st.checkbox("Debug Mode")
        bank_choice = st.selectbox("Bank Format", ["Maybank", "Generic"])
        now_dt      = _dt.datetime.now()
        imp_month   = st.selectbox(
            "Statement Month",
            list(range(1, 13)),
            index=now_dt.month - 1,
            format_func=lambda m: _dt.date(2000, m, 1).strftime("%B"),
        )
        imp_year = int(
            st.number_input("Statement Year", min_value=2000,
                            max_value=2035, value=now_dt.year, step=1)
        )
        uploaded_files = st.file_uploader(
            "Upload PDF Statements", type=["pdf"], accept_multiple_files=True
        )
    else:
        debug_mode     = False
        bank_choice    = "Maybank"
        uploaded_files = None
        imp_month      = None
        imp_year       = None

    st.markdown("---")

    # Statement Manager
    with st.expander("Statement Manager", expanded=False):
        stmts = list_statements()
        if stmts.empty:
            st.info("No statements imported yet.")
        else:
            for _, row in stmts.iterrows():
                mname = _cal.month_abbr[int(row["month"])]
                lc, rc = st.columns([3, 1])
                lc.markdown(
                    f"**{mname} {int(row['year'])}** — {int(row['num_rows'])} rows"
                )
                if rc.button("Del", key=f"del_{row['filename']}"):
                    delete_statement(row["filename"])
                    st.rerun()

    st.markdown("---")
    total_tx, total_stmts = get_db_stats()
    st.markdown(
        f"<small style='color:#8899aa;'>"
        f"{total_stmts} statement(s) &bull; {total_tx} transactions saved"
        f"</small>",
        unsafe_allow_html=True,
    )

# ── Import mode: parse and save new PDFs ──────────────────────────────────────
if mode == "Import New Statement" and uploaded_files:
    for file in uploaded_files:
        safe_name = f"{file.name}::{imp_year}-{imp_month:02d}"
        if statement_exists(safe_name):
            st.warning(
                f"**{file.name}** for "
                f"{_cal.month_name[imp_month]} {imp_year} was already imported. "
                "Delete it first from the Statement Manager if you want to re-import."
            )
            continue

        st.write(f"Processing `{file.name}`...")
        temp_path = f"temp_{file.name}"
        with open(temp_path, "wb") as fh:
            fh.write(file.getbuffer())
        try:
            if bank_choice == "Maybank":
                from parsers.maybank import MaybankParser
                parser = MaybankParser(temp_path)
            else:
                parser = GenericBankParser(temp_path)
            transactions_df = parser.extract_transactions()
            balance         = parser.extract_ending_balance()
            if transactions_df is not None and not transactions_df.empty:
                processed = process_transactions(transactions_df)
                n = save_transactions(processed, safe_name, imp_month, imp_year)
                st.success(
                    f"Saved **{n}** transactions from `{file.name}` "
                    f"({_cal.month_name[imp_month]} {imp_year}). "
                    f"Ending Balance: RM {balance:,.2f}"
                )
            else:
                st.warning(f"No tables found in {file.name}.")
                if debug_mode:
                    import pdfplumber
                    with pdfplumber.open(temp_path) as pdf:
                        if pdf.pages:
                            raw_text = pdf.pages[0].extract_text()
                            st.text_area("Raw PDF Text", raw_text, height=300)
        except Exception as e:
            st.error(f"Error parsing {file.name}: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

# ── Load all data from DB ──────────────────────────────────────────────────────
clean_df = load_transactions()

if clean_df.empty:
    if mode == "Import New Statement":
        st.info("Upload a PDF statement above to get started.")
    else:
        st.info(
            "No saved data found. Switch to **Import New Statement** in the sidebar "
            "to add your first bank statement."
        )
    st.stop()

clean_df = clean_df.sort_values("Date")

# ── Sidebar Filters (rendered after data is ready) ────────────────────────────
with st.sidebar:
    st.markdown("---")
    st.markdown("### Filters")

    # Year multiselect
    all_years = sorted(clean_df["year"].dropna().unique().astype(int).tolist(), reverse=True)
    sel_years = st.multiselect("Year", all_years, default=all_years)

    # Month multiselect (only months present in data)
    all_months_raw = sorted(clean_df["month"].dropna().unique().astype(int).tolist())
    all_months = {m: _cal.month_name[m] for m in all_months_raw}
    sel_months = st.multiselect(
        "Month",
        options=list(all_months.keys()),
        default=list(all_months.keys()),
        format_func=lambda m: all_months.get(m, m),
    )

    # Date range (fine-grained)
    has_dates = clean_df["Date"].notna().any()
    if has_dates:
        min_d = clean_df["Date"].min().date()
        max_d = clean_df["Date"].max().date()
        date_range = st.date_input(
            "Date Range",
            value=(min_d, max_d),
            min_value=min_d,
            max_value=max_d,
        )
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            d_start, d_end = date_range
        else:
            d_start, d_end = min_d, max_d
    else:
        d_start, d_end = None, None

    # Transaction type
    all_types = sorted(clean_df["Type"].dropna().unique().tolist())
    sel_types = st.multiselect("Transaction Type", all_types, default=all_types)

    # Category
    all_cats = sorted(clean_df["Category"].dropna().unique().tolist())
    sel_cats = st.multiselect("Category", all_cats, default=all_cats)

    # Keyword search
    kw = st.text_input("Search Description", placeholder="e.g. Grab, TNB, FUND")

    # Amount range
    amt_abs = clean_df["Amount"].abs()
    if not amt_abs.empty:
        amt_min = float(amt_abs.min())
        amt_max = float(amt_abs.max())
        if amt_min < amt_max:
            amt_range = st.slider(
                "Amount Range (RM)",
                min_value=amt_min,
                max_value=amt_max,
                value=(amt_min, amt_max),
                step=1.0,
            )
        else:
            amt_range = (amt_min, amt_max)
    else:
        amt_range = (0.0, 0.0)

    st.markdown("---")
    st.markdown(
        "<small style='color:#8899aa;'>Filters apply to all tabs.</small>",
        unsafe_allow_html=True,
    )

# ── Apply filters ─────────────────────────────────────────────────────────────
df = clean_df.copy()

if sel_years:
    df = df[df["year"].isin(sel_years)]

if sel_months:
    df = df[df["month"].isin(sel_months)]

if has_dates and d_start and d_end:
    df = df[
        (df["Date"].dt.date >= d_start) &
        (df["Date"].dt.date <= d_end)
    ]

if sel_types:
    df = df[df["Type"].isin(sel_types)]

if sel_cats:
    df = df[df["Category"].isin(sel_cats)]

if kw.strip():
    df = df[
        df["Description"].str.contains(kw.strip(), case=False, na=False)
    ]

df = df[df["Amount"].abs().between(amt_range[0], amt_range[1])]

# ── Show active filter summary ────────────────────────────────────────────────
total_rows = len(clean_df)
filtered   = len(df)
if filtered < total_rows:
    st.markdown(
        f"<small style='color:#feb019;'>Showing <b>{filtered}</b> of "
        f"<b>{total_rows}</b> transactions after filters.</small>",
        unsafe_allow_html=True,
    )

# ── Derived aggregates from filtered data ─────────────────────────────────────
savings_in_df  = df[df["Category"] == "Savings / Tabung"].copy()
savings_out_df = df[df["Category"] == "Tabung Withdrawal"].copy()

income_df      = df[(df["Type"] == "Income") & (df["Category"] != "Tabung Withdrawal")]
expense_df     = df[(df["Type"] == "Expense") & (df["Category"] != "Savings / Tabung")].copy()

expense_df["Amount"]    = expense_df["Amount"].abs()
savings_in_df["Amount"] = savings_in_df["Amount"].abs()

total_income       = income_df["Amount"].sum()
total_expenses     = expense_df["Amount"].sum()
total_savings_in   = savings_in_df["Amount"].sum()
total_savings_out  = savings_out_df["Amount"].sum()

net_flow           = total_income - total_expenses
savings_rate = (
    (net_flow + total_savings_in) / total_income * 100
    if total_income > 0 else 0.0
)

cat_summary = (
    expense_df.groupby("Category")["Amount"]
    .sum().reset_index()
    .sort_values("Amount", ascending=False)
)
top_cat     = cat_summary.iloc[0]["Category"] if not cat_summary.empty else "N/A"
top_cat_amt = cat_summary.iloc[0]["Amount"]   if not cat_summary.empty else 0.0
net_remaining = total_income - total_expenses - total_savings_in + total_savings_out

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Overview", "Cash Flow Map", "Weekly Analysis", "Monthly Trends", "Budgets & Targets"])


# =============================================================================
# TAB 1 — OVERVIEW
# =============================================================================
with tab1:
    st.subheader("All Transactions")
    st.dataframe(df, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Income vs Expenses")
        s = (
            df[df["Type"].isin(["Income", "Expense"])]
            .groupby("Type")["Amount"].sum().reset_index()
        )
        s.loc[s["Type"] == "Expense", "Amount"] = s.loc[
            s["Type"] == "Expense", "Amount"
        ].abs()
        fig1 = px.bar(
            s, x="Type", y="Amount", color="Type",
            color_discrete_map={"Income": "#00e396", "Expense": "#ff4560"},
            title="Total Income vs Expenses",
        )
        fig1.update_layout(**DARK)
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        st.subheader("Expenses by Category")
        if not cat_summary.empty:
            fig2 = px.pie(
                cat_summary, values="Amount", names="Category",
                hole=0.45, color_discrete_sequence=PAL,
                title="Spending Breakdown",
            )
            fig2.update_layout(**DARK)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No expense data to display.")

    st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)
    st.subheader("80/20 Expense Pareto Chart")
    if not cat_summary.empty:
        pareto_df = cat_summary.copy()
        pareto_df["CumPct"] = (pareto_df["Amount"].cumsum() / pareto_df["Amount"].sum()) * 100
        
        from plotly.subplots import make_subplots
        fig_p = make_subplots(specs=[[{"secondary_y": True}]])
        fig_p.add_trace(
            go.Bar(x=pareto_df["Category"], y=pareto_df["Amount"], name="Amount", marker_color="#775dd0"),
            secondary_y=False,
        )
        fig_p.add_trace(
            go.Scatter(x=pareto_df["Category"], y=pareto_df["CumPct"], name="Cumulative %", marker_color="#00e396", mode="lines+markers"),
            secondary_y=True,
        )
        fig_p.add_hline(y=80, line_dash="dot", line_color="#feb019", annotation_text="80% Threshold", secondary_y=True)
        fig_p.update_layout(**DARK, title="Categories driving 80% of costs", height=400)
        fig_p.update_yaxes(title_text="Amount (RM)", secondary_y=False)
        fig_p.update_yaxes(title_text="Cumulative %", range=[0, 105], secondary_y=True)
        st.plotly_chart(fig_p, use_container_width=True)

# =============================================================================
# TAB 2 — CASH FLOW MAP
# =============================================================================
with tab2:

    # KPI Cards
    net_class = "positive" if net_flow >= 0 else "negative"
    net_label = "Surplus" if net_flow >= 0 else "Deficit"
    sr_class  = "positive" if savings_rate >= 20 else (
        "neutral" if savings_rate >= 5 else "negative"
    )
    sr_label  = "Healthy" if savings_rate >= 20 else "Below target"

    st.markdown(
        f"""
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-icon">Income</div>
            <div class="kpi-label">Total Income</div>
            <div class="kpi-value positive">RM {total_income:,.2f}</div>
            <div class="kpi-sub positive">All inflows</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-icon">Expenses</div>
            <div class="kpi-label">Total Expenses</div>
            <div class="kpi-value negative">RM {total_expenses:,.2f}</div>
            <div class="kpi-sub negative">All outflows</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-icon">Tabung</div>
            <div class="kpi-label">Savings / Tabung</div>
            <div class="kpi-value savings">RM {total_savings_in:,.2f}</div>
            <div class="kpi-sub savings">Transferred to funds</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-icon">Net</div>
            <div class="kpi-label">Net Cash Flow</div>
            <div class="kpi-value {net_class}">RM {net_flow:,.2f}</div>
            <div class="kpi-sub {net_class}">{net_label} this period</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-icon">Rate</div>
            <div class="kpi-label">Savings Rate</div>
            <div class="kpi-value {sr_class}">{savings_rate:.1f}%</div>
            <div class="kpi-sub {sr_class}">{sr_label}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-icon">Top</div>
            <div class="kpi-label">Biggest Expense</div>
            <div class="kpi-value neutral" style="font-size:1.05rem;">{top_cat}</div>
            <div class="kpi-sub neutral">RM {top_cat_amt:,.2f} spent</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)

    # Sankey
    st.markdown(
        '<div class="section-header">Cash Flow Sankey Map</div>',
        unsafe_allow_html=True,
    )
    nodes       = ["Your Income", "Cash Pool"]
    node_colors = ["#00e396", "#775dd0"]
    srcs, tgts, vals, lcolors = [], [], [], []

    if total_income > 0:
        srcs.append(0); tgts.append(1)
        vals.append(total_income); lcolors.append("rgba(0,227,150,0.35)")

    if total_savings_out > 0:
        nodes.append("Saving out (Withdrawal)"); node_colors.append("#feb019")
        srcs.append(len(nodes)-1); tgts.append(1)
        vals.append(total_savings_out); lcolors.append("rgba(254,176,25,0.35)")

    if total_expenses > (total_income + total_savings_out):
        nodes.append("Deficit"); node_colors.append("#ff4560")
        srcs.append(len(nodes)-1); tgts.append(1)
        vals.append(total_expenses - (total_income + total_savings_out))
        lcolors.append("rgba(255,69,96,0.35)")

    for i, (_, row) in enumerate(cat_summary.iterrows()):
        if row["Amount"] > 0:
            nodes.append(row["Category"])
            node_colors.append(PAL[i % len(PAL)])
            srcs.append(1); tgts.append(len(nodes)-1)
            vals.append(row["Amount"])
            r, g, b = px.colors.hex_to_rgb(PAL[i % len(PAL)])
            lcolors.append(f"rgba({r},{g},{b},0.4)")

    if total_savings_in > 0:
        nodes.append("Saving in (Tabung)"); node_colors.append("#00b4d8")
        srcs.append(1); tgts.append(len(nodes)-1)
        vals.append(total_savings_in); lcolors.append("rgba(0,180,216,0.5)")

    if net_remaining > 0:
        nodes.append("Net Remaining"); node_colors.append("#26de81")
        srcs.append(1); tgts.append(len(nodes)-1)
        vals.append(net_remaining); lcolors.append("rgba(38,222,129,0.5)")

    fig_s = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=18, thickness=22,
            line=dict(color="rgba(255,255,255,0.08)", width=0.5),
            label=nodes, color=node_colors,
            hovertemplate="<b>%{label}</b><br>RM %{value:,.2f}<extra></extra>",
        ),
        link=dict(
            source=srcs, target=tgts, value=vals, color=lcolors,
            hovertemplate=(
                "<b>%{source.label}</b> to <b>%{target.label}</b>"
                "<br>RM %{value:,.2f}<extra></extra>"
            ),
        ),
    ))
    fig_s.update_layout(
        **DARK,
        title=dict(text="Monthly Cash Flow", font=dict(size=16, color="#c8d6e5")),
        height=480,
    )
    st.plotly_chart(fig_s, use_container_width=True)
    st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)

    # Waterfall + Treemap
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            '<div class="section-header">Waterfall — Income to Net Flow</div>',
            unsafe_allow_html=True,
        )
        wf_x = ["Income"] + cat_summary["Category"].tolist()
        wf_y = [total_income] + (-cat_summary["Amount"]).tolist()
        wf_m = ["absolute"] + ["relative"] * len(cat_summary)
        if total_savings_out > 0:
            wf_x.append("Saving out"); wf_y.append(total_savings_out)
            wf_m.append("relative")
        if total_savings_in > 0:
            wf_x.append("Saving in"); wf_y.append(-total_savings_in)
            wf_m.append("relative")
        wf_x.append("Net Flow")
        wf_y.append(net_remaining if net_remaining >= 0 else net_flow)
        wf_m.append("total")

        fig_wf = go.Figure(go.Waterfall(
            orientation="v", measure=wf_m, x=wf_x, y=wf_y,
            texttemplate="RM %{y:,.0f}", textposition="outside",
            connector=dict(line=dict(color="rgba(255,255,255,0.15)", width=1, dash="dot")),
            increasing=dict(marker=dict(color="#00e396")),
            decreasing=dict(marker=dict(color="#ff4560")),
            totals=dict(marker=dict(color="#00b4d8")),
        ))
        fig_wf.update_layout(
            **DARK,
            title=dict(text="From Income to Net Savings",
                       font=dict(size=14, color="#c8d6e5")),
            yaxis=dict(tickprefix="RM ", gridcolor="rgba(255,255,255,0.06)"),
            xaxis=dict(tickangle=-30), height=400,
        )
        st.plotly_chart(fig_wf, use_container_width=True)

    with col_b:
        st.markdown(
            '<div class="section-header">Expense Treemap</div>',
            unsafe_allow_html=True,
        )
        if not cat_summary.empty:
            fig_tree = px.treemap(
                cat_summary, path=["Category"], values="Amount",
                color="Amount",
                color_continuous_scale=["#1e2130", "#775dd0", "#ff4560"],
                title="Spending Breakdown by Category",
            )
            fig_tree.update_traces(
                texttemplate="<b>%{label}</b><br>RM %{value:,.0f}",
                hovertemplate=(
                    "<b>%{label}</b><br>RM %{value:,.2f}"
                    " (%{percentRoot:.1%})<extra></extra>"
                ),
            )
            fig_tree.update_layout(
                **DARK, coloraxis_showscale=False, height=400,
                title=dict(font=dict(size=14, color="#c8d6e5")),
            )
            st.plotly_chart(fig_tree, use_container_width=True)
        else:
            st.info("No expense data to display.")

    st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)

    # Ranked bar + Gauge
    col_c, col_d = st.columns([3, 2])
    with col_c:
        st.markdown(
            '<div class="section-header">Expense Category Rankings</div>',
            unsafe_allow_html=True,
        )
        if not cat_summary.empty:
            ranked = cat_summary.sort_values("Amount", ascending=True)
            pct = (
                (ranked["Amount"] / total_expenses * 100).round(1)
                if total_expenses > 0 else [0] * len(ranked)
            )
            fig_bar = go.Figure(go.Bar(
                x=ranked["Amount"], y=ranked["Category"], orientation="h",
                text=[f"RM {v:,.0f}  ({p}%)" for v, p in zip(ranked["Amount"], pct)],
                textposition="outside",
                marker=dict(
                    color=ranked["Amount"],
                    colorscale=[[0, "#775dd0"], [0.5, "#feb019"], [1, "#ff4560"]],
                    line=dict(width=0),
                ),
            ))
            fig_bar.update_layout(
                **DARK,
                title=dict(text="Spending by Category (Low to High)",
                           font=dict(size=14, color="#c8d6e5")),
                xaxis=dict(tickprefix="RM ", gridcolor="rgba(255,255,255,0.06)"),
                yaxis=dict(automargin=True), height=380,
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    with col_d:
        st.markdown(
            '<div class="section-header">Savings Rate Gauge</div>',
            unsafe_allow_html=True,
        )
        gc = (
            "#00e396" if savings_rate >= 20
            else ("#feb019" if savings_rate >= 5 else "#ff4560")
        )
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=max(0.0, savings_rate),
            number=dict(suffix="%", font=dict(size=36, color="#c8d6e5")),
            delta=dict(reference=20, increasing=dict(color="#00e396"),
                       decreasing=dict(color="#ff4560"), suffix="%"),
            gauge=dict(
                axis=dict(range=[0, 60], tickcolor="#8899aa",
                          tickwidth=1, tickfont=dict(color="#8899aa")),
                bar=dict(color=gc, thickness=0.3),
                bgcolor="rgba(0,0,0,0)", borderwidth=0,
                steps=[
                    dict(range=[0,  5],  color="rgba(255,69,96,0.15)"),
                    dict(range=[5,  20], color="rgba(254,176,25,0.15)"),
                    dict(range=[20, 60], color="rgba(0,227,150,0.15)"),
                ],
                threshold=dict(line=dict(color="#ffffff", width=2),
                               thickness=0.8, value=20),
            ),
            title=dict(text="Savings Rate (Target 20%)",
                       font=dict(size=15, color="#c8d6e5")),
        ))
        fig_g.update_layout(**DARK, height=380)
        st.plotly_chart(fig_g, use_container_width=True)

    st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)

    # Pareto
    st.markdown(
        '<div class="section-header">Pareto Analysis — Where Does Your Money Go?</div>',
        unsafe_allow_html=True,
    )
    if not cat_summary.empty:
        pareto = cat_summary.sort_values("Amount", ascending=False).reset_index(drop=True)
        pareto["Cumulative %"] = (
            pareto["Amount"].cumsum() / pareto["Amount"].sum() * 100
        ).round(1)
        fig_p = make_subplots(specs=[[{"secondary_y": True}]])
        fig_p.add_trace(
            go.Bar(
                x=pareto["Category"], y=pareto["Amount"], name="Amount",
                marker=dict(color=PAL[:len(pareto)], line=dict(width=0)),
                text=[f"RM {v:,.0f}" for v in pareto["Amount"]],
                textposition="outside",
            ), secondary_y=False,
        )
        fig_p.add_trace(
            go.Scatter(
                x=pareto["Category"], y=pareto["Cumulative %"],
                name="Cumulative %", mode="lines+markers",
                line=dict(color="#feb019", width=2.5),
                marker=dict(size=7, color="#feb019"),
            ), secondary_y=True,
        )
        fig_p.add_hline(
            y=80, secondary_y=True,
            line=dict(color="rgba(255,255,255,0.25)", dash="dash", width=1),
        )
        fig_p.update_layout(
            **DARK,
            title=dict(text="Pareto Chart — Top Spending Categories (80/20 Rule)",
                       font=dict(size=14, color="#c8d6e5")),
            yaxis=dict(title="Amount (RM)", tickprefix="RM ",
                       gridcolor="rgba(255,255,255,0.06)"),
            yaxis2=dict(title="Cumulative %", ticksuffix="%", range=[0, 110]),
            legend=dict(orientation="h", y=1.12, bgcolor="rgba(0,0,0,0)"),
            height=400, bargap=0.3,
        )
        st.plotly_chart(fig_p, use_container_width=True)
    else:
        st.info("No expense data available for Pareto analysis.")


# =============================================================================
# TAB 3 — WEEKLY ANALYSIS
# =============================================================================
with tab3:

    if not has_dates or df["Date"].isna().all():
        st.warning(
            "No date information found in your transactions. "
            "Weekly analysis requires a Date column."
        )
        st.stop()

    # Build weekly aggregated dataframe
    wdf = df.dropna(subset=["Date"]).copy()
    wdf["Week"]      = wdf["Date"].dt.to_period("W").apply(lambda r: r.start_time)
    wdf["WeekLabel"] = wdf["Date"].dt.to_period("W").astype(str)
    wdf["DayOfWeek"] = wdf["Date"].dt.day_name()
    wdf["DayNum"]    = wdf["Date"].dt.dayofweek      # 0=Mon … 6=Sun

    # -- Weekly income / expense / savings pivot ----------------------------
    inc_w  = (wdf[wdf["Type"] == "Income"]
              .groupby("Week")["Amount"].sum().reset_index()
              .rename(columns={"Amount": "Income"}))
    exp_w  = (wdf[wdf["Type"] == "Expense"].copy()
              .assign(Amount=lambda x: x["Amount"].abs())
              .groupby("Week")["Amount"].sum().reset_index()
              .rename(columns={"Amount": "Expense"}))
    sav_w  = (wdf[wdf["Type"] == "Savings Transfer"].copy()
              .assign(Amount=lambda x: x["Amount"].abs())
              .groupby("Week")["Amount"].sum().reset_index()
              .rename(columns={"Amount": "Savings"}))

    weekly = (
        inc_w
        .merge(exp_w, on="Week", how="outer")
        .merge(sav_w, on="Week", how="outer")
        .fillna(0)
        .sort_values("Week")
    )
    weekly["Net"]        = weekly["Income"] - weekly["Expense"]
    weekly["WeekLabel"]  = weekly["Week"].dt.strftime("W%W\n%d %b")
    weekly["NetClass"]   = weekly["Net"].apply(lambda v: "Surplus" if v >= 0 else "Deficit")

    # ── SECTION 1: Weekly KPI strip ─────────────────────────────────────────
    num_weeks   = len(weekly)
    best_week_i = weekly["Net"].idxmax() if not weekly.empty else None
    worst_week_i= weekly["Net"].idxmin() if not weekly.empty else None
    best_week   = weekly.loc[best_week_i, "WeekLabel"].replace("\n", " ") if best_week_i is not None else "N/A"
    worst_week  = weekly.loc[worst_week_i, "WeekLabel"].replace("\n", " ") if worst_week_i is not None else "N/A"
    avg_weekly_exp = weekly["Expense"].mean() if not weekly.empty else 0
    avg_weekly_inc = weekly["Income"].mean()  if not weekly.empty else 0

    st.markdown(
        f"""
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-icon">Weeks</div>
            <div class="kpi-label">Weeks Analyzed</div>
            <div class="kpi-value neutral">{num_weeks}</div>
            <div class="kpi-sub neutral">Total periods</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-icon">Avg In</div>
            <div class="kpi-label">Avg Weekly Income</div>
            <div class="kpi-value positive">RM {avg_weekly_inc:,.2f}</div>
            <div class="kpi-sub positive">Per week</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-icon">Avg Out</div>
            <div class="kpi-label">Avg Weekly Expense</div>
            <div class="kpi-value negative">RM {avg_weekly_exp:,.2f}</div>
            <div class="kpi-sub negative">Per week</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-icon">Best</div>
            <div class="kpi-label">Best Week (Net)</div>
            <div class="kpi-value positive" style="font-size:1.05rem;">{best_week}</div>
            <div class="kpi-sub positive">RM {weekly.loc[best_week_i, "Net"]:,.2f} surplus</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-icon">Worst</div>
            <div class="kpi-label">Worst Week (Net)</div>
            <div class="kpi-value negative" style="font-size:1.05rem;">{worst_week}</div>
            <div class="kpi-sub negative">RM {abs(weekly.loc[worst_week_i, "Net"]):,.2f} deficit</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)

    # ── VISUAL 1: Grouped bar — weekly income vs expense ──────────────────
    st.markdown(
        '<div class="section-header-week">Weekly Income vs Expenses</div>',
        unsafe_allow_html=True,
    )
    fig_wb = go.Figure()
    fig_wb.add_trace(go.Bar(
        x=weekly["WeekLabel"], y=weekly["Income"],
        name="Income", marker_color="#00e396",
        hovertemplate="<b>%{x}</b><br>Income: RM %{y:,.2f}<extra></extra>",
    ))
    fig_wb.add_trace(go.Bar(
        x=weekly["WeekLabel"], y=weekly["Expense"],
        name="Expense", marker_color="#ff4560",
        hovertemplate="<b>%{x}</b><br>Expense: RM %{y:,.2f}<extra></extra>",
    ))
    fig_wb.add_trace(go.Bar(
        x=weekly["WeekLabel"], y=weekly["Savings"],
        name="Savings/Tabung", marker_color="#00b4d8",
        hovertemplate="<b>%{x}</b><br>Savings: RM %{y:,.2f}<extra></extra>",
    ))
    fig_wb.update_layout(
        **DARK,
        barmode="group",
        title=dict(text="Weekly Breakdown", font=dict(size=14, color="#c8d6e5")),
        xaxis=dict(tickangle=-20, gridcolor="rgba(255,255,255,0.04)"),
        yaxis=dict(tickprefix="RM ", gridcolor="rgba(255,255,255,0.06)"),
        legend=dict(orientation="h", y=1.1, bgcolor="rgba(0,0,0,0)"),
        bargap=0.25, bargroupgap=0.05,
        height=380,
    )
    st.plotly_chart(fig_wb, use_container_width=True)

    st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)

    # ── VISUAL 2: Net flow line with surplus / deficit fill ───────────────
    col_w1, col_w2 = st.columns(2)

    with col_w1:
        st.markdown(
            '<div class="section-header-week">Weekly Net Cash Flow</div>',
            unsafe_allow_html=True,
        )
        fig_net = go.Figure()
        # Positive area (surplus)
        fig_net.add_trace(go.Scatter(
            x=weekly["WeekLabel"], y=weekly["Net"].clip(lower=0),
            fill="tozeroy", fillcolor="rgba(0,227,150,0.15)",
            line=dict(color="rgba(0,0,0,0)"), showlegend=False, hoverinfo="skip",
        ))
        # Negative area (deficit)
        fig_net.add_trace(go.Scatter(
            x=weekly["WeekLabel"], y=weekly["Net"].clip(upper=0),
            fill="tozeroy", fillcolor="rgba(255,69,96,0.15)",
            line=dict(color="rgba(0,0,0,0)"), showlegend=False, hoverinfo="skip",
        ))
        # Main line
        fig_net.add_trace(go.Scatter(
            x=weekly["WeekLabel"], y=weekly["Net"],
            mode="lines+markers+text",
            name="Net Flow",
            line=dict(color="#feb019", width=2.5),
            marker=dict(
                size=9,
                color=["#00e396" if v >= 0 else "#ff4560" for v in weekly["Net"]],
                line=dict(color="#1e2130", width=2),
            ),
            text=[f"RM {v:,.0f}" for v in weekly["Net"]],
            textposition="top center",
            textfont=dict(size=9, color="#c8d6e5"),
            hovertemplate="<b>%{x}</b><br>Net: RM %{y:,.2f}<extra></extra>",
        ))
        fig_net.add_hline(
            y=0, line=dict(color="rgba(255,255,255,0.2)", dash="dot", width=1),
        )
        fig_net.update_layout(
            **DARK,
            title=dict(text="Surplus (green) / Deficit (red)",
                       font=dict(size=14, color="#c8d6e5")),
            xaxis=dict(tickangle=-20, gridcolor="rgba(255,255,255,0.04)"),
            yaxis=dict(tickprefix="RM ", gridcolor="rgba(255,255,255,0.06)"),
            showlegend=False, height=380,
        )
        st.plotly_chart(fig_net, use_container_width=True)

    with col_w2:
        st.markdown(
            '<div class="section-header-week">Weekly Spending Heatmap by Day</div>',
            unsafe_allow_html=True,
        )
        # Pivot: rows = day of week, cols = week label
        heat_df = (
            wdf[wdf["Type"] == "Expense"].copy()
            .assign(Amount=lambda x: x["Amount"].abs())
        )
        if not heat_df.empty:
            heat_df["WeekLabel2"] = heat_df["Date"].dt.strftime("Wk %d %b")
            pivot = (
                heat_df.groupby(["DayNum", "DayOfWeek", "WeekLabel2"])["Amount"]
                .sum().reset_index()
                .pivot_table(index="DayOfWeek", columns="WeekLabel2",
                             values="Amount", fill_value=0)
            )
            day_order = ["Monday","Tuesday","Wednesday","Thursday",
                         "Friday","Saturday","Sunday"]
            pivot = pivot.reindex([d for d in day_order if d in pivot.index])

            fig_heat = go.Figure(go.Heatmap(
                z=pivot.values,
                x=pivot.columns.tolist(),
                y=pivot.index.tolist(),
                colorscale=[
                    [0,   "#1e2130"],
                    [0.3, "#775dd0"],
                    [0.7, "#feb019"],
                    [1.0, "#ff4560"],
                ],
                hovertemplate=(
                    "<b>%{y}</b> — %{x}<br>"
                    "Spent: RM %{z:,.2f}<extra></extra>"
                ),
                colorbar=dict(
                    tickprefix="RM ",
                    tickfont=dict(color="#8899aa"),
                    outlinewidth=0,
                ),
            ))
            fig_heat.update_layout(
                **DARK,
                title=dict(text="Spending by Day (darker = more spending)",
                           font=dict(size=13, color="#c8d6e5")),
                xaxis=dict(tickangle=-25, tickfont=dict(size=9)),
                height=380,
            )
            st.plotly_chart(fig_heat, use_container_width=True)
        else:
            st.info("No expense data to build heatmap.")

    st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)

    # ── VISUAL 3: Stacked area — weekly spending by category ──────────────
    st.markdown(
        '<div class="section-header-week">Weekly Spending by Category (Stacked Area)</div>',
        unsafe_allow_html=True,
    )
    cat_week = (
        wdf[wdf["Type"] == "Expense"].copy()
        .assign(Amount=lambda x: x["Amount"].abs())
        .groupby(["Week", "Category"])["Amount"].sum()
        .reset_index()
        .sort_values("Week")
    )
    cat_week["WeekLabel"] = cat_week["Week"].dt.strftime("W%W %d %b")
    if not cat_week.empty:
        cats_present = cat_week.groupby("Category")["Amount"].sum().sort_values(ascending=False).index.tolist()
        fig_area = go.Figure()
        for i, cat in enumerate(cats_present):
            cdf = cat_week[cat_week["Category"] == cat]
            fig_area.add_trace(go.Scatter(
                x=cdf["WeekLabel"], y=cdf["Amount"],
                name=cat,
                mode="lines",
                stackgroup="one",
                fillcolor=f"rgba({','.join(str(int(c)) for c in px.colors.hex_to_rgb(PAL[i % len(PAL)]))},0.7)",
                line=dict(color=PAL[i % len(PAL)], width=0.5),
                hovertemplate=(
                    f"<b>{cat}</b><br>Week: %{{x}}"
                    "<br>RM %{y:,.2f}<extra></extra>"
                ),
            ))
        fig_area.update_layout(
            **DARK,
            title=dict(text="How Each Category Evolves Week by Week",
                       font=dict(size=14, color="#c8d6e5")),
            xaxis=dict(tickangle=-20, gridcolor="rgba(255,255,255,0.04)"),
            yaxis=dict(tickprefix="RM ", gridcolor="rgba(255,255,255,0.06)"),
            legend=dict(orientation="h", y=-0.25, bgcolor="rgba(0,0,0,0)",
                        font=dict(size=11)),
            height=420,
        )
        st.plotly_chart(fig_area, use_container_width=True)
    else:
        st.info("No expense data to display.")

    st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)

    # ── VISUAL 4: Week-over-week delta bar ────────────────────────────────
    st.markdown(
        '<div class="section-header-week">Week-over-Week Spending Change</div>',
        unsafe_allow_html=True,
    )
    if len(weekly) >= 2:
        wow = weekly[["WeekLabel", "Expense"]].copy()
        wow["Delta"]  = wow["Expense"].diff()
        wow["DeltaPct"] = (wow["Expense"].pct_change() * 100).round(1)
        wow = wow.dropna()

        wow_colors = ["#00e396" if v <= 0 else "#ff4560" for v in wow["Delta"]]
        fig_wow = go.Figure(go.Bar(
            x=wow["WeekLabel"],
            y=wow["Delta"],
            marker_color=wow_colors,
            text=[
                f"{'▲' if v > 0 else '▼'} {abs(v):,.0f} ({p:+.1f}%)"
                for v, p in zip(wow["Delta"], wow["DeltaPct"])
            ],
            textposition="outside",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Change vs prior week: RM %{y:,.2f}<extra></extra>"
            ),
        ))
        fig_wow.add_hline(
            y=0, line=dict(color="rgba(255,255,255,0.2)", dash="dot", width=1),
        )
        fig_wow.update_layout(
            **DARK,
            title=dict(
                text="Green = spent less than previous week | Red = spent more",
                font=dict(size=13, color="#c8d6e5"),
            ),
            xaxis=dict(tickangle=-20, gridcolor="rgba(255,255,255,0.04)"),
            yaxis=dict(tickprefix="RM ", gridcolor="rgba(255,255,255,0.06)"),
            height=360,
        )
        st.plotly_chart(fig_wow, use_container_width=True)
    else:
        st.info("Need at least 2 weeks of data to show week-over-week changes.")

    st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)

    # ── VISUAL 5: Weekly transaction table drill-down ─────────────────────
    st.markdown(
        '<div class="section-header-week">Drill-Down by Week</div>',
        unsafe_allow_html=True,
    )
    week_options = sorted(wdf["WeekLabel"].unique().tolist())
    if week_options:
        sel_week = st.selectbox("Select a week to inspect:", week_options)
        week_detail = wdf[wdf["WeekLabel"] == sel_week].copy()

        d1, d2, d3 = st.columns(3)
        w_inc = week_detail[week_detail["Type"] == "Income"]["Amount"].sum()
        w_exp = week_detail[week_detail["Type"] == "Expense"]["Amount"].abs().sum()
        w_net = w_inc - w_exp
        nc    = "positive" if w_net >= 0 else "negative"
        nl    = "Surplus" if w_net >= 0 else "Deficit"

        d1.metric("Income", f"RM {w_inc:,.2f}")
        d2.metric("Expenses", f"RM {w_exp:,.2f}")
        d3.metric("Net Flow", f"RM {w_net:,.2f}", delta=f"{nl}")

        col_det1, col_det2 = st.columns([2, 1])
        with col_det1:
            st.dataframe(
                week_detail[["Date","Description","Amount","Type","Category"]]
                .sort_values("Date"),
                use_container_width=True, height=300,
            )
        with col_det2:
            wd_exp = week_detail[week_detail["Type"] == "Expense"].copy()
            wd_exp["Amount"] = wd_exp["Amount"].abs()
            wd_cat = wd_exp.groupby("Category")["Amount"].sum().reset_index()
            if not wd_cat.empty:
                fig_dw = px.pie(
                    wd_cat, values="Amount", names="Category",
                    hole=0.5, color_discrete_sequence=PAL,
                    title="This Week's Spending",
                )
                fig_dw.update_layout(**DARK, height=300)
                st.plotly_chart(fig_dw, use_container_width=True)
            else:
                st.info("No expense history available for the selected range.")


# =============================================================================
# TAB 5 — BUDGETS & TARGETS
# =============================================================================
with tab5:
    st.markdown('<div class="section-header">Monthly Budget Targets</div>', unsafe_allow_html=True)
    st.write("Set your desired monthly spending and savings targets. These apply to any month you analyze.")
    
    from storage.database import load_budgets, save_budget
    budgets = load_budgets()
    
    from analysis.processor import RULES
    all_known_cats = sorted(list(set(r["category"] for r in RULES if r["category"] not in ["Salary / Income", "Transfer In", "Tabung Withdrawal"])))
    
    data_cats = set(expense_df["Category"].unique()).union(set(savings_in_df["Category"].unique()))
    all_cats = sorted(list(set(all_known_cats).union(data_cats)))
    
    col_l, col_r = st.columns([1, 2])
    
    with col_l:
        st.markdown("### Set Targets")
        with st.form("budget_form"):
            new_budgets = {}
            for cat in all_cats:
                current_val = budgets.get(cat, 0.0)
                new_budgets[cat] = st.number_input(cat, min_value=0.0, value=float(current_val), step=50.0)
                
            if st.form_submit_button("Save Targets"):
                for cat, amt in new_budgets.items():
                    save_budget(cat, amt)
                st.success("Budgets updated!")
                st.rerun()

    with col_r:
        st.markdown("### Budget vs Actual (Selected Period)")
        
        actuals = expense_df.groupby("Category")["Amount"].sum().to_dict()
        sav_actuals = savings_in_df.groupby("Category")["Amount"].sum().to_dict()
        actuals.update(sav_actuals)
        
        budget_data = []
        for cat in all_cats:
            target = budgets.get(cat, 0.0)
            actual = actuals.get(cat, 0.0)
            if target > 0 or actual > 0:
                budget_data.append({"Category": cat, "Target": target, "Actual": actual})
                
        if budget_data:
            bdf = pd.DataFrame(budget_data)
            bdf["% Used"] = (bdf["Actual"] / bdf["Target"].replace(0, float('inf')) * 100).round(1)
            
            fig_b = go.Figure()
            fig_b.add_trace(go.Bar(
                x=bdf["Category"], y=bdf["Target"], name="Target",
                marker_color="rgba(255,255,255,0.1)",
                marker_line_color="rgba(255,255,255,0.3)",
                marker_line_width=2
            ))
            
            colors = ["#ff4560" if row["Actual"] > row["Target"] and row["Target"] > 0 else "#00e396" for _, row in bdf.iterrows()]
            
            fig_b.add_trace(go.Bar(
                x=bdf["Category"], y=bdf["Actual"], name="Actual",
                marker_color=colors
            ))
            
            fig_b.update_layout(
                **DARK, barmode="overlay", height=500,
                title="Budget vs Actual Spending",
                yaxis_title="Amount (RM)"
            )
            st.plotly_chart(fig_b, use_container_width=True)
            
            st.dataframe(bdf.style.format({"Target": "{:.2f}", "Actual": "{:.2f}", "% Used": "{:.1f}%"}), use_container_width=True)
        else:
            st.info("Set some targets on the left to see the comparison.")



# =============================================================================
# TAB 4 — MONTHLY TRENDS
# =============================================================================
with tab4:

    # Use the full DB data (clean_df) so trends are unaffected by date-range filter
    mdf = clean_df.copy()

    if "year" not in mdf.columns or "month" not in mdf.columns:
        st.warning("Month/year metadata not found. Re-import statements to see this tab.")
        st.stop()

    # Build per-month aggregates
    inc_m  = (mdf[mdf["Type"] == "Income"]
              .groupby(["year", "month"])["Amount"].sum()
              .reset_index().rename(columns={"Amount": "Income"}))
    exp_m  = (mdf[mdf["Type"] == "Expense"].copy()
              .assign(Amount=lambda x: x["Amount"].abs())
              .groupby(["year", "month"])["Amount"].sum()
              .reset_index().rename(columns={"Amount": "Expense"}))
    sav_m  = (mdf[mdf["Category"] == "Savings / Tabung"].copy()
              .assign(Amount=lambda x: x["Amount"].abs())
              .groupby(["year", "month"])["Amount"].sum()
              .reset_index().rename(columns={"Amount": "Savings"}))

    monthly = (
        inc_m
        .merge(exp_m, on=["year", "month"], how="outer")
        .merge(sav_m, on=["year", "month"], how="outer")
        .fillna(0)
        .sort_values(["year", "month"])
    )
    monthly["MonthLabel"] = monthly.apply(
        lambda r: f"{_cal.month_abbr[int(r['month'])]} {int(r['year'])}", axis=1
    )
    monthly["Net"] = monthly["Income"] - monthly["Expense"]
    monthly["SavingsRate"] = (
        (monthly["Net"] + monthly["Savings"]) / monthly["Income"].replace(0, float("nan")) * 100
    ).fillna(0).round(1)
    monthly["Expense_Roll3"] = monthly["Expense"].rolling(3, min_periods=1).mean()
    monthly["Expense_MoM"]   = monthly["Expense"].diff()
    monthly["Expense_MoMPct"]= (monthly["Expense"].pct_change() * 100).round(1)

    num_months = len(monthly)

    # ── Monthly KPI strip ────────────────────────────────────────────────────
    best_m_i  = monthly["Net"].idxmax() if not monthly.empty else None
    worst_m_i = monthly["Net"].idxmin() if not monthly.empty else None
    avg_m_exp = monthly["Expense"].mean()
    avg_m_inc = monthly["Income"].mean()
    ytd_inc   = monthly["Income"].sum()
    ytd_exp   = monthly["Expense"].sum()
    ytd_sav   = monthly["Savings"].sum()
    ytd_net   = ytd_inc - ytd_exp

    st.markdown(
        f"""
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-icon">Months</div>
            <div class="kpi-label">Months on Record</div>
            <div class="kpi-value neutral">{num_months}</div>
            <div class="kpi-sub neutral">Total periods</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-icon">YTD In</div>
            <div class="kpi-label">Total Income</div>
            <div class="kpi-value positive">RM {ytd_inc:,.2f}</div>
            <div class="kpi-sub positive">All months</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-icon">YTD Out</div>
            <div class="kpi-label">Total Expenses</div>
            <div class="kpi-value negative">RM {ytd_exp:,.2f}</div>
            <div class="kpi-sub negative">All months</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-icon">Saved</div>
            <div class="kpi-label">Total Tabung</div>
            <div class="kpi-value savings">RM {ytd_sav:,.2f}</div>
            <div class="kpi-sub savings">Cumulative savings</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-icon">Net</div>
            <div class="kpi-label">Net Total</div>
            <div class="kpi-value {'positive' if ytd_net >= 0 else 'negative'}">RM {ytd_net:,.2f}</div>
            <div class="kpi-sub {'positive' if ytd_net >= 0 else 'negative'}">{'Surplus' if ytd_net >= 0 else 'Deficit'}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-icon">Avg/mo</div>
            <div class="kpi-label">Avg Monthly Spend</div>
            <div class="kpi-value neutral">RM {avg_m_exp:,.2f}</div>
            <div class="kpi-sub neutral">Per month</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)

    # ── VISUAL 1: Grouped monthly bar chart ──────────────────────────────────
    st.markdown(
        '<div class="section-header-week">Monthly Income vs Expenses vs Savings</div>',
        unsafe_allow_html=True,
    )
    fig_mb = go.Figure()
    fig_mb.add_trace(go.Bar(
        x=monthly["MonthLabel"], y=monthly["Income"],
        name="Income", marker_color="#00e396",
        hovertemplate="<b>%{x}</b><br>Income: RM %{y:,.2f}<extra></extra>",
    ))
    fig_mb.add_trace(go.Bar(
        x=monthly["MonthLabel"], y=monthly["Expense"],
        name="Expense", marker_color="#ff4560",
        hovertemplate="<b>%{x}</b><br>Expense: RM %{y:,.2f}<extra></extra>",
    ))
    fig_mb.add_trace(go.Bar(
        x=monthly["MonthLabel"], y=monthly["Savings"],
        name="Savings/Tabung", marker_color="#00b4d8",
        hovertemplate="<b>%{x}</b><br>Savings: RM %{y:,.2f}<extra></extra>",
    ))
    fig_mb.update_layout(
        **DARK,
        barmode="group",
        title=dict(text="Month-by-Month Breakdown", font=dict(size=14, color="#c8d6e5")),
        xaxis=dict(tickangle=-30, gridcolor="rgba(255,255,255,0.04)"),
        yaxis=dict(tickprefix="RM ", gridcolor="rgba(255,255,255,0.06)"),
        legend=dict(orientation="h", y=1.1, bgcolor="rgba(0,0,0,0)"),
        bargap=0.25, bargroupgap=0.05, height=400,
    )
    st.plotly_chart(fig_mb, use_container_width=True)

    st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)

    # ── VISUAL 2: Expense trend + rolling 3-month average ────────────────────
    col_m1, col_m2 = st.columns(2)

    with col_m1:
        st.markdown(
            '<div class="section-header-week">Expense Trend + 3-Month Rolling Avg</div>',
            unsafe_allow_html=True,
        )
        fig_roll = go.Figure()
        fig_roll.add_trace(go.Bar(
            x=monthly["MonthLabel"], y=monthly["Expense"],
            name="Monthly Expense",
            marker=dict(color="rgba(255,69,96,0.4)", line=dict(width=0)),
            hovertemplate="<b>%{x}</b><br>Expense: RM %{y:,.2f}<extra></extra>",
        ))
        fig_roll.add_trace(go.Scatter(
            x=monthly["MonthLabel"], y=monthly["Expense_Roll3"],
            name="3-Month Avg",
            mode="lines+markers",
            line=dict(color="#feb019", width=2.5),
            marker=dict(size=7, color="#feb019", line=dict(color="#1e2130", width=2)),
            hovertemplate="<b>%{x}</b><br>3M Avg: RM %{y:,.2f}<extra></extra>",
        ))
        fig_roll.update_layout(
            **DARK,
            title=dict(text="Is your spending trending up or down?",
                       font=dict(size=13, color="#c8d6e5")),
            xaxis=dict(tickangle=-30, gridcolor="rgba(255,255,255,0.04)"),
            yaxis=dict(tickprefix="RM ", gridcolor="rgba(255,255,255,0.06)"),
            legend=dict(orientation="h", y=1.1, bgcolor="rgba(0,0,0,0)"),
            height=370,
        )
        st.plotly_chart(fig_roll, use_container_width=True)

    with col_m2:
        st.markdown(
            '<div class="section-header-week">Monthly Savings Rate</div>',
            unsafe_allow_html=True,
        )
        sr_colors = [
            "#00e396" if v >= 20 else ("#feb019" if v >= 5 else "#ff4560")
            for v in monthly["SavingsRate"]
        ]
        fig_sr = go.Figure()
        fig_sr.add_trace(go.Bar(
            x=monthly["MonthLabel"], y=monthly["SavingsRate"],
            name="Savings Rate",
            marker=dict(color=sr_colors, line=dict(width=0)),
            text=[f"{v:.1f}%" for v in monthly["SavingsRate"]],
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Savings Rate: %{y:.1f}%<extra></extra>",
        ))
        fig_sr.add_hline(
            y=20,
            line=dict(color="rgba(255,255,255,0.3)", dash="dash", width=1.5),
            annotation_text="20% target",
            annotation_font=dict(color="#8899aa", size=11),
        )
        fig_sr.update_layout(
            **DARK,
            title=dict(text="Green = healthy (>20%) | Amber = OK (5-20%) | Red = low",
                       font=dict(size=12, color="#c8d6e5")),
            xaxis=dict(tickangle=-30, gridcolor="rgba(255,255,255,0.04)"),
            yaxis=dict(ticksuffix="%", gridcolor="rgba(255,255,255,0.06)", range=[0, max(monthly["SavingsRate"].max() * 1.3, 30)]),
            showlegend=False, height=370,
        )
        st.plotly_chart(fig_sr, use_container_width=True)

    st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)

    # ── VISUAL 3: Month-over-Month spending delta ─────────────────────────────
    st.markdown(
        '<div class="section-header-week">Month-over-Month Expense Change</div>',
        unsafe_allow_html=True,
    )
    if len(monthly) >= 2:
        mom = monthly.dropna(subset=["Expense_MoM"]).copy()
        mom_colors = ["#00e396" if v <= 0 else "#ff4560" for v in mom["Expense_MoM"]]
        fig_mom = go.Figure(go.Bar(
            x=mom["MonthLabel"],
            y=mom["Expense_MoM"],
            marker_color=mom_colors,
            text=[
                f"{'▲' if v > 0 else '▼'} RM {abs(v):,.0f} ({p:+.1f}%)"
                for v, p in zip(mom["Expense_MoM"], mom["Expense_MoMPct"])
            ],
            textposition="outside",
            hovertemplate=(
                "<b>%{x}</b><br>Change vs prior month: RM %{y:,.2f}<extra></extra>"
            ),
        ))
        fig_mom.add_hline(
            y=0, line=dict(color="rgba(255,255,255,0.2)", dash="dot", width=1),
        )
        fig_mom.update_layout(
            **DARK,
            title=dict(
                text="Green = spent less than previous month | Red = spent more",
                font=dict(size=13, color="#c8d6e5"),
            ),
            xaxis=dict(tickangle=-30, gridcolor="rgba(255,255,255,0.04)"),
            yaxis=dict(tickprefix="RM ", gridcolor="rgba(255,255,255,0.06)"),
            height=360,
        )
        st.plotly_chart(fig_mom, use_container_width=True)
    else:
        st.info("Import at least 2 months of statements to see month-over-month changes.")

    st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)

    # ── VISUAL 4: Monthly summary table ──────────────────────────────────────
    st.markdown(
        '<div class="section-header-week">Full Monthly Summary Table</div>',
        unsafe_allow_html=True,
    )
    display_monthly = monthly[[
        "MonthLabel", "Income", "Expense", "Savings", "Net", "SavingsRate"
    ]].copy()
    display_monthly = display_monthly.rename(columns={
        "MonthLabel":  "Month",
        "Income":      "Income (RM)",
        "Expense":     "Expense (RM)",
        "Savings":     "Tabung (RM)",
        "Net":         "Net Flow (RM)",
        "SavingsRate": "Savings Rate (%)",
    })
    # Format numeric columns
    for col in ["Income (RM)", "Expense (RM)", "Tabung (RM)", "Net Flow (RM)"]:
        display_monthly[col] = display_monthly[col].map(lambda v: f"RM {v:,.2f}")
    display_monthly["Savings Rate (%)"] = display_monthly["Savings Rate (%)"].map(
        lambda v: f"{v:.1f}%"
    )
    st.dataframe(display_monthly.set_index("Month"), use_container_width=True)
