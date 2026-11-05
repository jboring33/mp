import json
import os
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# Page Configuration
st.set_page_config(page_title="MP Master Hub", page_icon="🏛️", layout="wide")

# Purge residual URL query params to keep address bar clean
st.query_params.clear()

MASTER_CONFIG_URL = (
    "https://raw.githubusercontent.com/jboring33/MP/main/config.json"
)
README_GUIDE_URL = "https://raw.githubusercontent.com/jboring33/MP/main/README.md"
CONFIG_PATH = "config.json"


@st.cache_data(ttl=60)
def load_config():
  if os.path.exists(CONFIG_PATH):
    try:
      with open(CONFIG_PATH, "r") as f:
        return json.load(f)
    except Exception:
      pass
  try:
    response = requests.get(MASTER_CONFIG_URL, timeout=5)
    if response.status_code == 200:
      return response.json()
  except Exception:
    pass
  return {
      "benchmarks": ["SPY", "QQQ", "DIA", "IWM", "EFA", "EMXC"],
      "benchmark_descriptions": {},
      "benchmark_mapping": {},
      "asset_class_thresholds": {},
      "global_macro_universe": {},
  }


@st.cache_data(ttl=300)
def load_readme_guide():
  try:
    res = requests.get(README_GUIDE_URL, timeout=3)
    if res.status_code == 200:
      return res.text
  except Exception:
    pass
  return "Architecture guide currently unavailable offline."


config = load_config()

# --- Title & Sidebar Control Center ---
st.title("🏛️ MP Master Hub")
st.caption("Institutional Single Source of Truth Portfolio Engine")

st.sidebar.header("🛠️ Control Center & Settings")
strategy_engine = st.sidebar.selectbox(
    "Select Strategy Engine",
    [
        "💼 Current Portfolio & Rotation Engine",
        "🛡️ 90% Core ETF Strategy",
        "🚀 10% Satellite Stock Strategy",
    ],
)

st.sidebar.divider()

# --- Collapsible Sidebar: Institutional Criteria & RVOL Profiles ---
with st.sidebar.expander(
    "⚙️ Institutional Criteria & RVOL Profiles", expanded=False
):
  asset_profiles = config.get("asset_class_thresholds", {})
  selected_profile_name = st.selectbox(
      "Asset Class / Strategy Profile:", list(asset_profiles.keys())
  )
  selected_profile = asset_profiles.get(
      selected_profile_name, list(asset_profiles.values())[0]
  )

  active_rvol = st.slider(
      "Target RVOL Threshold",
      min_value=0.40,
      max_value=2.00,
      value=float(selected_profile.get("default_rvol", 0.80)),
      step=0.05,
  )
  max_dist_sma = st.slider(
      "Max Dist from 50 SMA (%)",
      min_value=0.005,
      max_value=0.100,
      value=float(selected_profile.get("max_dist_from_50sma_pct", 0.04)),
      step=0.005,
      format="%.3f",
  )
  min_ud_vol = st.slider(
      "Min Up/Down Volume Ratio",
      min_value=1.00,
      max_value=2.00,
      value=float(selected_profile.get("min_ud_vol_ratio", 1.15)),
      step=0.05,
  )
  buffer_pct = st.slider(
      "200-Day Buffer (%)",
      min_value=0.000,
      max_value=0.050,
      value=float(selected_profile.get("default_buffer_pct", 0.02)),
      step=0.005,
      format="%.3f",
  )

st.sidebar.divider()

# --- Collapsible Sidebar: Active Mappings ---
with st.sidebar.expander("🔍 Active Mappings & Descriptions", expanded=False):
  benchmark_mapping = config.get("benchmark_mapping", {})
  bench_descriptions = config.get("benchmark_descriptions", {})

  if benchmark_mapping:
    for ticker, details in benchmark_mapping.items():
      if isinstance(details, dict):
        bench = details.get("benchmark", "SPY")
        t_desc = details.get("description", "")
        asset_cls = details.get("asset_class", "Core")
      else:
        bench = details
        t_desc = ""
        asset_cls = "Core"

      b_desc = bench_descriptions.get(bench, f"{bench} Core Benchmark Index")

      with st.expander(f"{ticker} ➔ {bench} ({asset_cls})"):
        st.markdown(f"**Ticker Desc:** {t_desc}")
        st.markdown(f"**Benchmark:** {bench}")
        st.markdown(f"**Benchmark Desc:** {b_desc}")
  else:
    st.info("No custom benchmark mappings found in config.")

# --- Built-in Mapping & Index Guidance Expander ---
with st.sidebar.expander("💡 Benchmark Selection & Mapping Guide"):
  st.markdown("""
    When evaluating a ticker's long description (e.g., tracking an MSCI or FTSE index), use these mapping rules:
    * **US Large Cap / Broad Market (S&P/Russell):** Map to **`SPY`**
    * **US Tech & Growth (Nasdaq):** Map to **`QQQ`**
    * **US Value / Industrial / Dividends (Dow Jones):** Map to **`DIA`**
    * **US Small Cap (Russell 2000):** Map to **`IWM`**
    * **Developed International / Europe / Japan (MSCI EAFE / FTSE Developed):** Map to **`EFA`**
    * **Emerging Markets ex-China / India (MSCI/FTSE Ex-China):** Map to **`EMXC`**
    """)

# --- Dynamic README Guide Loader ---
with st.sidebar.expander("📖 System Architecture & Guide", expanded=False):
  st.markdown(load_readme_guide())


# --- Helper: Resolve Benchmark & Dual Description for Ticker ---
def get_resolved_benchmark_info(ticker):
  t = ticker.upper().strip()
  b_map = config.get("benchmark_mapping", {})
  b_desc_map = config.get("benchmark_descriptions", {})

  if t in b_map:
    info = b_map[t]
    if isinstance(info, dict):
      bench = info.get("benchmark", "SPY")
      t_desc = info.get("description", "")
    else:
      bench = info
      t_desc = ""
    b_desc = b_desc_map.get(bench, f"{bench} Benchmark")
    return bench, t_desc, b_desc

  if t == "INDA":
    return (
        "EMXC",
        "iShares MSCI India ETF",
        b_desc_map.get("EMXC", "Emerging Markets ex China"),
    )
  if t in ["EWJ", "VGK"]:
    return (
        "EFA",
        "International Developed ETF",
        b_desc_map.get("EFA", "Developed International"),
    )

  return "SPY", f"{t} Asset", b_desc_map.get("SPY", "SPDR S&P 500 ETF")


# --- Benchmark Regime Helper ---
def get_benchmark_regime(ticker_symbol):
  bench, _, _ = get_resolved_benchmark_info(ticker_symbol)
  if not bench:
    return "🟢 STANDALONE ASSET", f"({ticker_symbol} Evaluated on Own SMAs)"
  try:
    df = yf.download(
        bench, period="1y", interval="1d", auto_adjust=True, progress=False
    )
    if df.empty:
      return "🟢 FULL RISK-ON", f"{bench} Healthy"
    c = df["Close"].squeeze()
    price = float(c.iloc[-1])
    sma50 = float(c.rolling(50).mean().iloc[-1])
    sma200 = float(c.rolling(200).mean().iloc[-1])

    if price > sma200 and price > sma50:
      return "🟢 FULL RISK-ON", f"({bench} > 50 & 200 SMA)"
    elif price > sma200 and price <= sma50:
      return (
          "🟡 PULLBACK / CAUTION",
          f"({bench} broke below 50 SMA - Trim 50% to JAAA/JPST)",
      )
    else:
      return (
          "🔴 BEAR / RISK-OFF",
          f"({bench} < 200 SMA - Rotate 100% to SCYB/JAAA/JPST)",
      )
  except Exception:
    return "🟢 FULL RISK-ON", "Default"


# ==========================================
# 1. CURRENT PORTFOLIO & ROTATION ENGINE
# ==========================================
if strategy_engine == "💼 Current Portfolio & Rotation Engine":
  st.header("💼 Current Portfolio Holdings & Action Engine")
  st.markdown(
      "Persistent evaluation of your active holdings (ETFs & stocks) delivering"
      " precise **BUY, SELL, or HOLD** recommendations."
  )

  # Stage 1: Persistent & Editable List of Current Holdings
  default_holdings = "JAAA, JPST, SCHD, SPYI, QQQI"
  curr_input = st.text_area(
      "Stage 1: Persistent Portfolio Watchlist (Comma Separated):",
      value=default_holdings,
      height=75,
  )

  if curr_input.strip():
    holdings = [t.strip().upper() for t in curr_input.split(",") if t.strip()]

    st.subheader(
        "Stage 2 & 3: Technical Health, Regime Diagnostics & Action Recommendations"
    )
    if st.button("Evaluate Portfolio Actions", type="primary"):
      portfolio_results = []
      for t in holdings:
        try:
          df = yf.download(
              t, period="1y", interval="1d", auto_adjust=True, progress=False
          )
          if df.empty:
            continue
          c = df["Close"].squeeze()
          vol = df["Volume"].squeeze()
          price = float(c.iloc[-1])
          sma50 = float(c.rolling(50).mean().iloc[-1])
          sma200 = float(c.rolling(200).mean().iloc[-1])
          dist_200 = ((price - sma200) / sma200) * 100

          avg_vol = float(vol.rolling(20).mean().iloc[-1])
          cur_vol = float(vol.iloc[-1])
          rvol = cur_vol / avg_vol if avg_vol > 0 else 1.0

          bench, t_desc, b_desc = get_resolved_benchmark_info(t)
          regime, guidance = get_benchmark_regime(t)

          # Action recommendation logic
          if price >= sma200 and rvol >= active_rvol:
            action = "🟢 BUY / ACCUMULATE"
            reason = (
                f"Price (${price:.2f}) is above 200 SMA and RVOL ({rvol:.2f})"
                " confirms institutional accumulation."
            )
          elif price < sma200:
            action = "🔴 SELL / ROTATE"
            reason = (
                f"Price (${price:.2f}) breached 200-day trend support. Risk-off"
                " rotation recommended."
            )
          elif price < sma50:
            action = "🟡 HOLD / TRIM"
            reason = (
                f"Price (${price:.2f}) pulled back below 50 SMA. Monitor trend"
                " support."
            )
          else:
            action = "🟢 HOLD"
            reason = (
                f"Technical structure stable above key moving averages."
                f" {guidance}"
            )

          portfolio_results.append({
              "Ticker": t,
              "Description": t_desc,
              "Price": round(price, 2),
              "Action": action,
              "Reason Why": reason,
              "Benchmark": bench,
              "RVOL": round(rvol, 2),
          })
        except Exception as e:
          st.error(f"Error evaluating {t}: {e}")

      if portfolio_results:
        st.dataframe(
            pd.DataFrame(portfolio_results),
            use_container_width=True,
            hide_index=True,
        )
  else:
    st.info("Please enter your portfolio holdings above.")

# ==========================================
# 2. 90% CORE ETF STRATEGY
# ==========================================
elif strategy_engine == "🛡️ 90% Core ETF Strategy":
  st.header("🛡️ 90% Core ETF Allocation Workflow")

  core_tab1, core_tab2, core_tab3 = st.tabs([
      "Stage 1: Core ETF Watchlist",
      "Stage 2: Intrinsic Value & Dip Filter",
      "Stage 3: 200-Day Trend Triggers",
  ])

  with core_tab1:
    st.subheader("Stage 1: Persistent Core ETF Watchlist & Mapping Audit")
    default_core = "SCHD, SPYI, QQQI, JAAA, JPST"
    core_input = st.text_area(
        "Edit Core ETF Watchlist (Comma Separated):",
        value=default_core,
        height=75,
    )

    core_tickers = [
        t.strip().upper() for t in core_input.split(",") if t.strip()
    ]

    # Explicit Mapping Alert Check
    b_map = config.get("benchmark_mapping", {})
    benchmarks_list = config.get("benchmarks", [])
    unmapped_core = [
        t
        for t in core_tickers
        if t not in b_map and t not in benchmarks_list
    ]

    if unmapped_core:
      st.error(
          f"🚨 **Unmapped Tickers Detected:** {', '.join(unmapped_core)}. Please"
          " add them to `benchmark_mapping` in your `config.json` file!"
      )
    else:
      st.success(
          "✅ All Stage 1 Core ETFs are successfully mapped against active"
          " benchmark proxies."
      )

    st.markdown("Verified tickers automatically pass down to Stages 2 and 3.")

  with core_tab2:
    st.subheader(
        "Stage 2: Intrinsic Value & Institutional Dip Filter (Passed from Stage"
        " 1)"
    )
    if core_tickers:
      if st.button("Run Intrinsic Valuation & Dip Check", type="primary"):
        iv_results = []
        for t in core_tickers:
          try:
            df = yf.download(
                t, period="1y", interval="1d", auto_adjust=True, progress=False
            )
            if df.empty:
              continue
            c = df["Close"].squeeze()
            vol = df["Volume"].squeeze()
            p = float(c.iloc[-1])
            sma50 = float(c.rolling(50).mean().iloc[-1])
            sma200 = (
                float(c.rolling(200).mean().iloc[-1])
                if len(c) >= 200
                else p
            )

            avg_vol = float(vol.rolling(20).mean().iloc[-1])
            rvol = float(vol.iloc[-1]) / avg_vol if avg_vol > 0 else 1.0
            dist_50 = (p - sma50) / sma50

            val_status = (
                "Accumulate / Fair Value"
                if p >= (sma200 * (1.0 - buffer_pct))
                and abs(dist_50) <= max_dist_sma
                else (
                    "Deep Value / Discount"
                    if p < (sma200 * (1.0 - buffer_pct))
                    else "Extended / Caution"
                )
            )

            bench, t_desc, _ = get_resolved_benchmark_info(t)

            iv_results.append({
                "Ticker": t,
                "Description": t_desc,
                "Price": round(p, 2),
                "50 SMA": round(sma50, 2),
                "200 SMA Buffer": round(sma200 * (1.0 - buffer_pct), 2),
                "RVOL": round(rvol, 2),
                "Benchmark": bench,
                "Valuation & Dip Status": val_status,
            })
          except Exception:
            pass
        if iv_results:
          st.dataframe(
              pd.DataFrame(iv_results), use_container_width=True, hide_index=True
          )
    else:
      st.warning("Please configure your tickers in Stage 1.")

  with core_tab3:
    st.subheader(
        "Stage 3: 200-Day Macro Trend Triggers (Passed from Stage 1)"
    )
    if core_tickers:
      if st.button("Run Trend Trigger Audit", type="primary"):
        trigger_rows = []
        for t in core_tickers:
          try:
            df = yf.download(
                t, period="1y", interval="1d", auto_adjust=True, progress=False
            )
            if df.empty:
              continue
            c = df["Close"].squeeze()
            price = float(c.iloc[-1])
            sma50 = float(c.rolling(50).mean().iloc[-1])
            sma200 = float(c.rolling(200).mean().iloc[-1])
            status = (
                "🟢 Bullish (Above MAs)"
                if price > sma200 and price > sma50
                else (
                    "🟡 Pullback (Below 50 SMA)"
                    if price > sma200
                    else "🔴 Bear Trend"
                )
            )
            trigger_rows.append(
                {"Ticker": t, "Price": round(price, 2), "Trend Status": status}
            )
          except Exception:
            pass
        if trigger_rows:
          st.dataframe(
              pd.DataFrame(trigger_rows),
              use_container_width=True,
              hide_index=True,
          )
    else:
      st.warning("Please configure your tickers in Stage 1.")

# ==========================================
# 3. 10% SATELLITE STOCK STRATEGY (SWING TRADE STOCKS)
# ==========================================
elif strategy_engine == "🚀 10% Satellite Stock Strategy":
  st.header("🚀 10% Satellite Stock Strategy: Swing Trade Stocks")

  sat_tab1, sat_tab2, sat_tab3 = st.tabs([
      "Stage 1: Satellite Stock Watchlist",
      "Stage 2: Institutional Accumulation & Dip Evaluation",
      "Stage 3: STP Dynamic Rotation (50 SMA & 20 EMA)",
  ])

  with sat_tab1:
    st.subheader("Stage 1: Persistent Satellite Equity Watchlist")
    default_sat = "NVDA, META, AMZN, MSFT, AAPL"
    sat_input = st.text_area(
        "Edit Satellite Stock Watchlist (Comma Separated):",
        value=default_sat,
        height=75,
    )
    sat_tickers = [
        t.strip().upper() for t in sat_input.split(",") if t.strip()
    ]
    st.success(
        f"Loaded {len(sat_tickers)} active satellite stocks. Passed to Stages 2"
        " and 3."
    )

  with sat_tab2:
    st.subheader(
        "Stage 2: Institutional Accumulation / Distribution & Dip Evaluation"
    )
    if sat_tickers:
      if st.button(
          "Run Institutional Dip & Accumulation Evaluation", type="primary"
      ):
        eval_rows = []
        for t in sat_tickers:
          try:
            df = yf.download(
                t, period="1y", interval="1d", auto_adjust=True, progress=False
            )
            if df.empty:
              continue
            c = df["Close"].squeeze()
            vol = df["Volume"].squeeze()
            price = float(c.iloc[-1])
            sma50 = float(c.rolling(50).mean().iloc[-1])
            sma200 = float(c.rolling(200).mean().iloc[-1])
            dist_50 = ((price - sma50) / sma50) * 100

            avg_vol = float(vol.rolling(20).mean().iloc[-1])
            cur_vol = float(vol.iloc[-1])
            rvol = cur_vol / avg_vol if avg_vol > 0 else 1.0

            flow_status = (
                "🟢 Institutional Accumulation (RVOL > Target & Healthy Dip)"
                if rvol >= active_rvol and price >= sma200
                else (
                    "🔴 Distribution / Risk (Low Volume / Falling Knife Risk)"
                    if rvol < active_rvol
                    else "🟡 Neutral / Watch"
                )
            )

            eval_rows.append({
                "Ticker": t,
                "Price": round(price, 2),
                "RVOL": round(rvol, 2),
                "50 SMA Distance": f"{dist_50:+.2f}%",
                "Institutional Flow Status": flow_status,
            })
          except Exception as e:
            st.error(f"Error evaluating {t}: {e}")
        if eval_rows:
          st.dataframe(
              pd.DataFrame(eval_rows), use_container_width=True, hide_index=True
          )
    else:
      st.warning("Please configure your watchlist in Stage 1.")

  with sat_tab3:
    st.subheader(
        "Stage 3: STP Swing Trade Portfolio Dynamic Rotation (50 SMA & 20 EMA)"
    )
    st.markdown(
        "_Ready for upcoming Swing Trade Portfolio (STP) module integration._"
    )
    if sat_tickers:
      if st.button("Run STP Dynamic Rotation Check", type="primary"):
        stp_rows = []
        for t in sat_tickers:
          try:
            df = yf.download(
                t, period="6mo", interval="1d", auto_adjust=True, progress=False
            )
            if df.empty:
              continue
            c = df["Close"].squeeze()
            price = float(c.iloc[-1])
            ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
            sma50 = float(c.rolling(50).mean().iloc[-1])

            signal = (
                "🟢 BULLISH CROSS (Price > 20 EMA > 50 SMA)"
                if price > ema20 and ema20 > sma50
                else (
                    "🟡 CAUTION / PULLBACK"
                    if price > sma50
                    else "🔴 BEARISH / EXIT"
                )
            )
            stp_rows.append({
                "Ticker": t,
                "Price": round(price, 2),
                "20 EMA": round(ema20, 2),
                "50 SMA": round(sma50, 2),
                "STP Signal": signal,
            })
          except Exception:
            pass
        if stp_rows:
          st.dataframe(
              pd.DataFrame(stp_rows), use_container_width=True, hide_index=True
          )
    else:
      st.warning("Please configure your watchlist in Stage 1.")
