from datetime import datetime
import json
import os
import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# Page Configuration
st.set_page_config(
    page_title="MP - Master Portfolio Hub",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling for Financial UI
st.markdown(
    """
    <style>
    .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .metric-card {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 0.75rem;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .status-badge {
        font-weight: 600;
        padding: 0.25rem 0.5rem;
        border-radius: 0.375rem;
    }
    dataframe, table, th, td {
        white-space: normal !important;
        word-wrap: break-word !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- MASTER CENTRAL CONFIG LOADER ---
# Set your raw GitHub config URL here
MASTER_CONFIG_URL = (
    "https://raw.githubusercontent.com/jboring33/MP/main/config.json"
)
CONFIG_FILE = "config.json"
STATE_FILE = "persistent_portfolio_state.json"


@st.cache_data(ttl=60)
def load_master_config():
  """Loads configuration from GitHub raw URL with local fallback."""
  if os.path.exists(CONFIG_FILE):
    try:
      with open(CONFIG_FILE, "r") as f:
        return json.load(f)
    except Exception:
      pass
  try:
    response = requests.get(MASTER_CONFIG_URL, timeout=5)
    if response.status_code == 200:
      return response.json()
  except Exception:
    pass

  # Default Fallback with Dynamic Ex-China Global Universes
  return {
      "benchmarks": ["SPY", "QQQ", "VT"],
      "global_macro_universe": {
          "US Broad Equity": "SPY",
          "US Tech Growth": "QQQ",
          "US Small Cap": "IWM",
          "Japan Equity": "EWJ",
          "India Momentum": "INDA",
          "Europe Broad": "VGK",
          "Latin America": "ILF",
          "Emerging Ex-China": "EMXC",
          "Global Dividend/Income": "VYMI",
          "Treasury Safe Harbor": "TLT",
      },
      "default_stock_universe": [
          "NVDA",
          "META",
          "AMZN",
          "MSFT",
          "AAPL",
          "GOOGL",
          "TSLA",
          "AMD",
          "AVGO",
          "ASML",
          "SONY",
          "HDB",
      ],
      "preset_configs": {
          "Watching": {
              "tickers": "SPY, QQQ, INDA, EWJ, EMXC",
              "buffer": 2.0,
              "rvol": 0.80,
              "min_atr": 0.50,
          },
          "Current Holds": {
              "tickers": "SPYI, QQQI, JAAA, JPST, SCYB",
              "buffer": 1.5,
              "rvol": 0.75,
              "min_atr": 0.25,
          },
      },
  }


master_config = load_master_config()

# --- BULLETPROOF STATE & URL PERSISTENCE ---
def sync_query_and_session_state():
  """Persists watchlist and parameter state between sessions and sleep cycles."""
  query = st.query_params

  # Sync Active Strategy Engine
  if "engine" in query:
    st.session_state["active_engine"] = query["engine"]
  elif "active_engine" not in st.session_state:
    st.session_state["active_engine"] = "🛡️ 90% Core ETF Strategy"

  # Sync Core ETF Tickers
  if "core_tickers" in query:
    st.session_state["core_tickers"] = query["core_tickers"]
  elif "core_tickers" not in st.session_state:
    st.session_state["core_tickers"] = master_config.get(
        "preset_configs", {}
    ).get("Watching", {}).get("tickers", "SPY, QQQ, INDA, EWJ, EMXC")

  # Sync Satellite Stock Tickers
  if "stock_tickers" in query:
    st.session_state["stock_tickers"] = query["stock_tickers"]
  elif "stock_tickers" not in st.session_state:
    st.session_state["stock_tickers"] = ", ".join(
        master_config.get("default_stock_universe", ["NVDA", "META", "AMZN"])
    )

  # Sync Current Active Portfolio Holds
  if "portfolio_holds" in query:
    st.session_state["portfolio_holds"] = query["portfolio_holds"]
  elif "portfolio_holds" not in st.session_state:
    st.session_state["portfolio_holds"] = master_config.get(
        "preset_configs", {}
    ).get("Current Holds", {}).get("tickers", "SPYI, QQQI, JAAA, JPST, SCYB")


sync_query_and_session_state()


def update_state_and_url(key, value):
  """Callback helper to record UI changes permanently to query string."""
  st.session_state[key] = value
  st.query_params[key] = value


# --- TECHNICAL CALCULATIONS ENGINE ---
def clean_df(df):
  if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)
  return df


def calculate_atr(df, window=14):
  h, l, c = df["High"], df["Low"], df["Close"]
  tr = pd.concat(
      [h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1
  ).max(axis=1)
  return float(tr.rolling(window).mean().iloc[-1])


def calculate_up_down_vol_ratio(df):
  if "Close" not in df.columns or "Volume" not in df.columns:
    return 1.0
  diff = df["Close"].diff()
  up_v = df.loc[diff > 0, "Volume"].sum()
  down_v = df.loc[diff < 0, "Volume"].sum()
  return float(up_v / down_v) if down_v > 0 else 2.0


def analyze_asset_trends(
    tickers_list, default_buffer=0.02, rvol_min=0.8, atr_min=0.5
):
  results = []
  for t in tickers_list:
    try:
      df = yf.download(
          t, period="2y", interval="1d", auto_adjust=True, progress=False
      )
      df = clean_df(df)
      if df.empty or len(df) < 50:
        continue

      c = df["Close"].squeeze()
      h = df["High"].squeeze()
      l = df["Low"].squeeze()
      o = df["Open"].squeeze()
      v = df["Volume"].squeeze()

      price = float(c.iloc[-1])
      vol = float(v.iloc[-1])
      v_sma20 = (
          float(v.rolling(20).mean().iloc[-1])
          if len(v) >= 20
          else float(v.mean())
      )
      rvol = vol / v_sma20 if v_sma20 > 0 else 1.0

      baseline_200 = (
          float(c.rolling(200).mean().iloc[-1])
          if len(c) >= 200
          else float(c.mean())
      )
      sma50 = (
          float(c.rolling(50).mean().iloc[-1])
          if len(c) >= 50
          else baseline_200
      )
      ema20 = (
          float(c.ewm(span=20, adjust=False).mean().iloc[-1])
          if len(c) >= 20
          else price
      )

      df_clean = pd.DataFrame({"High": h, "Low": l, "Close": c, "Open": o})
      atr = calculate_atr(df_clean)
      atr_pct = (atr / price) * 100

      eff_buf = max(default_buffer, (atr / price) * 1.5)
      u_th = baseline_200 * (1.0 + eff_buf)
      l_th = baseline_200 * (1.0 - eff_buf)

      pct_200 = ((price - baseline_200) / baseline_200) * 100.0
      dist_50_pct = ((price - sma50) / sma50) * 100.0

      # Signal Matrix
      if price > u_th and price >= ema20 and rvol >= rvol_min:
        action = "🟢 ACCUMULATE"
      elif price > u_th:
        action = "🟢 HOLD"
      elif l_th <= price <= u_th:
        action = "⚪ BUFFER ZONE"
      elif price < l_th:
        action = "🔴 SELL / ROTATE"
      else:
        action = "🟡 CAUTION"

      results.append({
          "Ticker": t,
          "Action Signal": action,
          "Price": round(price, 2),
          "200 SMA": round(baseline_200, 2),
          "% vs 200 SMA": f"{pct_200:+.2f}%",
          "50 SMA": round(sma50, 2),
          "Dist 50 SMA": f"{dist_50_pct:+.2f}%",
          "RVOL": f"{rvol:.2f}x",
          "ATR (%)": f"{atr_pct:.2f}%",
      })
    except Exception:
      pass
  return pd.DataFrame(results)


# --- SIDEBAR CONTROL PANEL ---
st.sidebar.title("🏛️ MP Master Hub")
st.sidebar.caption("Single Source of Truth Portfolio Engine")

engine_choice = st.sidebar.radio(
    "Select Strategy Engine",
    [
        "🛡️ 90% Core ETF Strategy",
        "🚀 10% Satellite Stock Strategy",
        "💼 Current Portfolio & Rotation Engine",
    ],
    index=[
        "🛡️ 90% Core ETF Strategy",
        "🚀 10% Satellite Stock Strategy",
        "💼 Current Portfolio & Rotation Engine",
    ].index(st.session_state["active_engine"]),
    key="engine_selector",
    on_change=lambda: update_state_and_url(
        "engine", st.session_state.engine_selector
    ),
)

st.sidebar.divider()

with st.sidebar.expander("📖 **System Architecture & Guide**", expanded=False):
  st.markdown("""
    ### Master Hub Architecture
    * **Single Source of Truth:** Centralized parameters loaded from GitHub (`jboring33/MP`).
    * **State Guard:** Changes persist in URL parameters and session state across app sleeping cycles.
    * **Ex-China Mandate:** Global Asset screening explicitly isolates domestic and ex-China emerging/developed foreign markets.
    * **Safe Harbor Rules:** Automatic allocation guidance between Risk-On equities and capital protection assets (`SCYB`, `JAAA`, `JPST`).
    """)

# --- MAIN ENGINE ROUTING ---

st.title(f"Master Hub Hub: {engine_choice.split(' ', 1)[1]}")
st.caption(f"Sync Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.divider()

# ==========================================
# ENGINE 1: 90% CORE ETF STRATEGY
# ==========================================
if engine_choice.startswith("🛡️"):
  core_tab1, core_tab2, core_tab3 = st.tabs([
      "Stage 1: RT Core ETF Screener",
      "Stage 2: Intrinsic Value (IVP)",
      "Stage 3: 200-Day Trend Triggers",
  ])

  # STAGE 1: RT CORE ETF SCREENER
  with core_tab1:
    st.subheader("Stage 1: Global Macro & Sector Relative Strength")
    st.markdown(
        "Scan broad asset classes and ex-China foreign universes for"
        " structural momentum."
    )

    macro_dict = master_config.get("global_macro_universe", {})
    st.json(macro_dict, expanded=False)

    core_tickers_input = st.text_area(
        "Active Core ETF Watchlist (Editable):",
        value=st.session_state.get("core_tickers", "SPY, QQQ, INDA, EWJ, EMXC"),
        key="core_input_field",
        on_change=lambda: update_state_and_url(
            "core_tickers", st.session_state.core_input_field
        ),
    )

    if st.button(
        "🚀 Run Stage 1 Macro Screen", type="primary", key="btn_run_stage1"
    ):
      t_list = [
          t.strip().upper()
          for t in core_tickers_input.split(",")
          if t.strip()
      ]
      with st.spinner("Screening global asset classes..."):
        df_core_res = analyze_asset_trends(t_list)
      if not df_core_res.empty:
        st.session_state["last_core_screener_results"] = df_core_res
        st.success(
            f"Screened {len(df_core_res)} assets. Results synced to Stage 2"
            " and Stage 3!"
        )

    if "last_core_screener_results" in st.session_state:
      st.dataframe(
          st.session_state["last_core_screener_results"],
          use_container_width=True,
          hide_index=True,
      )

  # STAGE 2: INTRINSIC VALUE (IVP)
  with core_tab2:
    st.subheader("Stage 2: Intrinsic Value & Yield Assessment")
    st.markdown(
        "Valuation models and distribution yields for active core portfolio"
        " candidate ETFs."
    )

    active_core_list = [
        t.strip().upper()
        for t in st.session_state.get("core_tickers", "").split(",")
        if t.strip()
    ]
    st.info(f"Evaluating valuation for active watch candidate: {active_core_list}")

    val_data = []
    for t in active_core_list:
      try:
        ticker_obj = yf.Ticker(t)
        info = ticker_obj.info
        val_data.append({
            "Ticker": t,
            "Name": info.get("shortName", t),
            "Yield (%)": (
                f"{(info.get('yield', 0) or 0) * 100:.2f}%"
                if info.get("yield")
                else "N/A"
            ),
            "52W High": info.get("fiftyTwoWeekHigh", "N/A"),
            "52W Low": info.get("fiftyTwoWeekLow", "N/A"),
            "Category": info.get("category", "ETF / Fund"),
        })
      except Exception:
        pass

    if val_data:
      st.dataframe(pd.DataFrame(val_data), use_container_width=True, hide_index=True)

  # STAGE 3: 200-DAY TREND TRIGGERS
  with core_tab3:
    st.subheader("Stage 3: 200-Day Macro Trend Execution Matrix")
    st.markdown(
        "Final execution rules and trend guardrails for 90% core positions."
    )

    if st.button("Evaluate 200-Day Guardrails", type="primary"):
      active_list = [
          t.strip().upper()
          for t in st.session_state.get("core_tickers", "").split(",")
          if t.strip()
      ]
      with st.spinner("Running 200 SMA & RVOL Matrix..."):
        df_200 = analyze_asset_trends(active_list)
      st.dataframe(df_200, use_container_width=True, hide_index=True)

# ==========================================
# ENGINE 2: 10% SATELLITE STOCK STRATEGY
# ==========================================
elif engine_choice.startswith("🚀"):
  sat_tab1, sat_tab2 = st.tabs([
      "Stage 1: Dynamic Stock Screener",
      "Stage 2: Institutional Dip & Tech Eval",
  ])

  # STAGE 1: DYNAMIC STOCK SCREENER
  with sat_tab1:
    st.subheader("Stage 1: Satellite Stock Screening & Discovery")
    st.markdown(
        "Screen candidate equities for institutional accumulation and initial"
        " setup filters."
    )

    stock_tickers_input = st.text_area(
        "Active Satellite Stock Watchlist (Editable):",
        value=st.session_state.get(
            "stock_tickers", "NVDA, META, AMZN, MSFT, AAPL, GOOGL"
        ),
        key="stock_input_field",
        on_change=lambda: update_state_and_url(
            "stock_tickers", st.session_state.stock_input_field
        ),
    )

    c1, c2 = st.columns(2)
    with c1:
      max_dist = st.slider("Max Distance from 50 SMA (%)", 0.0, 10.0, 4.0, 0.5)
    with c2:
      min_ud_vol = st.slider("Min Up/Down Volume Ratio", 0.8, 2.0, 1.15, 0.05)

    if st.button(
        "Run Stage 1 Stock Discovery", type="primary", key="btn_run_sat_stage1"
    ):
      t_list = [
          t.strip().upper()
          for t in stock_tickers_input.split(",")
          if t.strip()
      ]
      screened_results = []

      for t in t_list:
        try:
          df = yf.download(
              t, period="1y", interval="1d", auto_adjust=True, progress=False
          )
          df = clean_df(df)
          if df.empty or len(df) < 50:
            continue
          c = df["Close"].squeeze()
          price = float(c.iloc[-1])
          sma50 = float(c.rolling(50).mean().iloc[-1])
          dist_50 = ((price - sma50) / sma50) * 100.0
          ud_ratio = calculate_up_down_vol_ratio(df)

          # Pass candidates through screener checks
          passed = (dist_50 <= max_dist) and (ud_ratio >= min_ud_vol)

          screened_results.append({
              "Ticker": t,
              "Passed Filter": "✅ YES" if passed else "❌ NO",
              "Price": round(price, 2),
              "50 SMA": round(sma50, 2),
              "Dist 50 SMA (%)": f"{dist_50:+.2f}%",
              "U/D Vol Ratio": round(ud_ratio, 2),
          })
        except Exception:
          pass

      df_sat_res = pd.DataFrame(screened_results)
      st.session_state["stage1_stock_results"] = df_sat_res
      st.success(
          f"Screening complete! Processed {len(df_sat_res)} stock candidates."
      )

    if "stage1_stock_results" in st.session_state:
      st.dataframe(
          st.session_state["stage1_stock_results"],
          use_container_width=True,
          hide_index=True,
      )

  # STAGE 2: INSTITUTIONAL DIP & TECH EVAL (ZERO TICKER LOSS)
  with sat_tab2:
    st.subheader(
        "Stage 2: Technical Evaluation & Institutional Dip Diagnostics"
    )
    st.markdown(
        "Full detailed breakdown of all tickers shortlisted in Stage 1 without"
        " dropped assets."
    )

    all_satellite_tickers = [
        t.strip().upper()
        for t in st.session_state.get("stock_tickers", "").split(",")
        if t.strip()
    ]

    st.info(
        "Stage 2 input pipeline fully synchronized with Stage 1 list:"
        f" **{all_satellite_tickers}**"
    )

    if st.button("Run Full Stage 2 Technical Diagnostic", type="primary"):
      with st.spinner("Analyzing moving average structures & RVOL..."):
        df_sat_stage2 = analyze_asset_trends(all_satellite_tickers)
      if not df_sat_stage2.empty:
        st.dataframe(df_sat_stage2, use_container_width=True, hide_index=True)

# ==========================================
# ENGINE 3: CURRENT PORTFOLIO & ROTATION MATRIX
# ==========================================
elif engine_choice.startswith("💼"):
  st.subheader("💼 Active Holdings & Safe Harbor Rotation Engine")
  st.markdown(
      "Real-time benchmark regime analysis (**SPY** and **QQQ**) governing"
      " rotation into risk-off safe harbors (**SCYB**, **JAAA**, **JPST**)."
  )

  # Editable Holdings Input
  holdings_input = st.text_area(
      "Your Active Current Portfolio Holdings (Comma Separated):",
      value=st.session_state.get(
          "portfolio_holds", "SPYI, QQQI, JAAA, JPST, SCYB"
      ),
      key="holds_input_field",
      on_change=lambda: update_state_and_url(
          "portfolio_holds", st.session_state.holds_input_field
      ),
  )

  st.divider()

  # 1. Benchmark Macro Regime Matrix
  st.markdown("### 1. Macro Benchmark Regime Diagnostics")
  bench_data = []
  for b in ["SPY", "QQQ"]:
    try:
      df_b = yf.download(
          b, period="1y", interval="1d", auto_adjust=True, progress=False
      )
      df_b = clean_df(df_b)
      if not df_b.empty:
        c_b = df_b["Close"].squeeze()
        p_b = float(c_b.iloc[-1])
        s50_b = float(c_b.rolling(50).mean().iloc[-1])
        s200_b = float(c_b.rolling(200).mean().iloc[-1])

        if p_b > s200_b and p_b > s50_b:
          regime = "🟢 FULL RISK-ON"
          guidance = (
              "Hold 100% Risk-On Core & Growth Exposure (SPYI / QQQI / Stocks)"
          )
        elif p_b > s200_b and p_b <= s50_b:
          regime = "🟡 PULLBACK / CAUTION"
          guidance = (
              "Trim 50% of Risk Exposure to Safe Harbor Credit (JAAA / JPST)"
          )
        else:
          regime = "🔴 FULL BEAR / RISK-OFF"
          guidance = (
              "Rotate 100% to Capital Protection & Income (SCYB / JAAA / JPST)"
          )

        bench_data.append({
            "Benchmark": b,
            "Price": round(p_b, 2),
            "50 SMA": round(s50_b, 2),
            "200 SMA": round(s200_b, 2),
            "Regime Status": regime,
            "Recommended Portfolio Action": guidance,
        })
    except Exception:
      pass

  if bench_data:
    st.table(pd.DataFrame(bench_data))

  st.divider()

  # 2. Portfolio Holdings Execution Status
  st.markdown("### 2. Active Holdings Status & Technical Health")
  holdings_list = [
      t.strip().upper() for t in holdings_input.split(",") if t.strip()
  ]

  if st.button("Assess Active Portfolio Status", type="primary"):
    with st.spinner("Fetching live prices & moving averages..."):
      df_holdings_eval = analyze_asset_trends(holdings_list)
    if not df_holdings_eval.empty:
      st.dataframe(
          df_holdings_eval, use_container_width=True, hide_index=True
      )
