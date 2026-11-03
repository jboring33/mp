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
    page_title="MP Master Hub", page_icon="🏛️", layout="wide"
)

MASTER_CONFIG_URL = (
    "https://raw.githubusercontent.com/jboring33/MP/main/config.json"
)
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
      "benchmark_mapping": {},
      "global_macro_universe": {},
      "criteria_thresholds": {},
  }


config = load_config()
config_mapping = config.get("benchmark_mapping", {})


# --- Interactive Benchmark Interceptor & Snippet Generator ---
def render_config_snippet_generator(tickers_list, config):
  """Checks tickers against config.json benchmark_mapping and regional maps.

  If any are unmapped, prompts for selection and outputs the exact JSON snippet
  to copy-paste into GitHub config.json.
  """
  known_benchmarks = config.get(
      "benchmarks", ["SPY", "QQQ", "DIA", "IWM", "EFA", "EMXC"]
  )
  cfg_map = config.get("benchmark_mapping", {})
  macro_universe = config.get("global_macro_universe", {})

  resolved_map = {}
  unmapped = []

  # Automatic regional and country mappings
  auto_regional_map = {
      "INDA": "EMXC",
      "EWJ": "EFA",
      "VGK": "EFA",
  }

  for t in tickers_list:
    t = t.upper().strip()
    if not t:
      continue

    # 1. Core benchmarks or standalone hard assets
    if t in known_benchmarks or t in ["GLD", "IAU", "IBIT"]:
      resolved_map[t] = None if t in ["GLD", "IAU", "IBIT"] else t
    # 2. Config mapping file
    elif t in cfg_map:
      val = cfg_map[t]
      resolved_map[t] = None if val == "None" else val
    # 3. Known regional/macro maps
    elif t in auto_regional_map:
      resolved_map[t] = auto_regional_map[t]
    elif t in macro_universe.values():
      resolved_map[t] = "SPY"
    else:
      unmapped.append(t)

  if unmapped:
    st.warning(
        f"⚠️ **Action Required:** Unmapped Ticker(s) Detected —"
        f" `{', '.join(unmapped)}`"
    )
    st.markdown(
        "Please assign a benchmark below to generate your `config.json` update"
        " snippet for GitHub:"
    )

    for t in unmapped:
      col1, col2 = st.columns([1, 2])
      with col1:
        st.write(f"**{t}**")
      with col2:
        choice = st.selectbox(
            f"Select Benchmark for {t}",
            ["SPY", "QQQ", "DIA", "IWM", "EFA", "EMXC", "None (Standalone)"],
            key=f"gen_snippet_{t}",
        )
        val = "None" if choice == "None (Standalone)" else choice
        resolved_map[t] = None if val == "None" else val

        st.markdown(
            "📋 Copy this line into your GitHub `config.json`"
            " `benchmark_mapping` dictionary:"
        )
        st.code(f'"{t}": "{val}",', language="json")

    st.stop()  # Pauses execution until config is updated or acknowledged

  return resolved_map


# --- URL & Session State Synchronization ---
def sync_query_and_session_state(key, default_val):
  if key not in st.session_state:
    val = st.query_params.get(key, default_val)
    if isinstance(val, list):
      val = val[0] if val else default_val
    st.session_state[key] = val
  else:
    try:
      st.query_params[key] = st.session_state[key]
    except Exception:
      pass
  return st.session_state[key]


# Initialize Watchlists & Inputs (Blank initial states)
sync_query_and_session_state("core_watchlist", "")
sync_query_and_session_state("stock_watchlist", "")
sync_query_and_session_state("current_portfolio_tickers", "")
sync_query_and_session_state("satellite_scanned_tickers", "")


# --- Benchmark Regime Helper ---
def get_benchmark_regime(ticker_symbol, mapping):
  bench = mapping.get(ticker_symbol, "SPY")
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


# --- Title & Sidebar Navigation ---
st.title("🏛️ MP Master Hub")
st.caption("Single Source of Truth Portfolio Engine")

st.sidebar.header("Select Strategy Engine")
strategy_engine = st.sidebar.radio(
    "Choose Engine",
    [
        "🛡️ 90% Core ETF Strategy",
        "🚀 10% Satellite Stock Strategy",
        "💼 Current Portfolio & Rotation Engine",
    ],
)

with st.sidebar.expander("📖 System Architecture & Guide"):
  st.markdown("""
    * **90% Core ETF:** Macro relative strength (RT) ➔ Intrinsic Value (IVP) ➔ 200-Day Trend Triggers.
    * **10% Satellite:** Dynamic screener ➔ Institutional dip evaluation ➔ Tactical watchlist execution.
    * **Current Portfolio:** Live holdings monitor & multi-benchmark safe-harbor rotation matrix.
    """)

# Sidebar Audit View for Active Mappings
with st.sidebar.expander("🔍 View Active Benchmark Mappings"):
  st.markdown("Current mapping rules loaded from `config.json`:")
  combined_mappings = config.get("benchmark_mapping", {}).copy()
  combined_mappings.update({"INDA": "EMXC", "EWJ": "EFA", "VGK": "EFA"})
  mapping_df = pd.DataFrame(
      list(combined_mappings.items()), columns=["Ticker", "Assigned Benchmark"]
  )
  st.dataframe(mapping_df, use_container_width=True, hide_index=True)

st.sidebar.divider()

# ==========================================
# 1. CURRENT PORTFOLIO & ROTATION ENGINE
# ==========================================
if strategy_engine == "💼 Current Portfolio & Rotation Engine":
  st.header("💼 Current Portfolio Holdings & Multi-Benchmark Rotation Matrix")
  st.markdown(
      "Real-time benchmark regime analysis governing rotation into risk-off safe"
      " harbors (`SCYB`, `JAAA`, `JPST`)."
  )

  curr_input = st.text_input(
      "Your Active Current Portfolio Holdings (Comma Separated):",
      value=st.session_state.current_portfolio_tickers,
      placeholder="e.g., JAAA, JPST, SCHD, SPYI, VOO",
  )
  st.session_state.current_portfolio_tickers = curr_input

  if curr_input.strip():
    holdings = [t.strip().upper() for t in curr_input.split(",") if t.strip()]
    resolved_benchmarks = render_config_snippet_generator(holdings, config)

    st.subheader("1. Macro Benchmark Regime Diagnostics")
    benchmarks = config.get(
        "benchmarks", ["SPY", "QQQ", "DIA", "IWM", "EFA", "EMXC"]
    )
    rot_data = []
    for b in benchmarks:
      try:
        df = yf.download(
            b, period="1y", interval="1d", auto_adjust=True, progress=False
        )
        if df.empty:
          continue
        c = df["Close"].squeeze()
        price = float(c.iloc[-1])
        sma50 = float(c.rolling(50).mean().iloc[-1])
        sma200 = float(c.rolling(200).mean().iloc[-1])
        regime, action = get_benchmark_regime(b, config_mapping)
        rot_data.append({
            "Benchmark": b,
            "Price": round(price, 2),
            "50 SMA": round(sma50, 2),
            "200 SMA": round(sma200, 2),
            "Regime Status": regime,
            "Recommended Portfolio Action": action,
        })
      except Exception:
        pass

    if rot_data:
      st.dataframe(
          pd.DataFrame(rot_data), use_container_width=True, hide_index=True
      )

    st.subheader("2. Active Holdings Status & Technical Health")
    if st.button("Assess Active Portfolio Status", type="primary"):
      portfolio_results = []
      for t in holdings:
        try:
          df = yf.download(
              t, period="1y", interval="1d", auto_adjust=True, progress=False
          )
          if df.empty:
            continue
          c = df["Close"].squeeze()
          price = float(c.iloc[-1])
          sma200 = float(c.rolling(200).mean().iloc[-1])
          dist_200 = ((price - sma200) / sma200) * 100
          bench = resolved_benchmarks.get(t, "SPY")
          regime, guidance = get_benchmark_regime(t, resolved_benchmarks)
          portfolio_results.append({
              "Ticker": t,
              "Price": round(price, 2),
              "Assigned Benchmark": bench if bench else "None (Standalone)",
              "Regime Status": regime,
              "% vs 200 SMA": f"{dist_200:+.2f}%",
              "Rotation Guidance": guidance,
          })
        except Exception as e:
          st.error(f"Error loading {t}: {e}")
      if portfolio_results:
        st.dataframe(
            pd.DataFrame(portfolio_results),
            use_container_width=True,
            hide_index=True,
        )
  else:
    st.info("Please enter your current portfolio holdings above to begin.")

# ==========================================
# 2. 90% CORE ETF STRATEGY
# ==========================================
elif strategy_engine == "🛡️ 90% Core ETF Strategy":
  st.header("🛡️ 90% Core ETF Allocation Workflow")

  core_tab1, core_tab2, core_tab3 = st.tabs([
      "Stage 1: RT Core Screener",
      "Stage 2: Intrinsic Value (IVP)",
      "Stage 3: 200-Day Triggers",
  ])

  with core_tab1:
    st.subheader("Stage 1: Relative Strength & Capital Flow (RT)")
    selected_bench = st.selectbox(
        "Select Benchmark for Relative Strength",
        config.get("benchmarks", ["SPY"]),
    )
    universe = config.get("global_macro_universe", {})

    if st.button("Run Core ETF Macro Scan", type="primary"):
      scan_rows = []
      for name, sym in universe.items():
        try:
          df = yf.download(
              [sym, selected_bench],
              period="6mo",
              interval="1d",
              auto_adjust=True,
              progress=False,
          )["Close"]
          if sym in df.columns and selected_bench in df.columns:
            ret_sym = (df[sym].iloc[-1] / df[sym].iloc[0]) - 1
            ret_bench = (
                df[selected_bench].iloc[-1] / df[selected_bench].iloc[0]
            ) - 1
            alpha = ret_sym - ret_bench
            scan_rows.append({
                "Asset": name,
                "Ticker": sym,
                "6M Return": f"{ret_sym*100:.2f}%",
                "Alpha vs Benchmark": f"{alpha*100:+.2f}%",
            })
        except Exception:
          pass
      if scan_rows:
        df_scan = pd.DataFrame(scan_rows)
        st.dataframe(df_scan, use_container_width=True, hide_index=True)
        st.session_state.core_watchlist = ",".join(df_scan["Ticker"].tolist())
        st.success("Top macro assets automatically recommended to Core Watchlist!")

  with core_tab2:
    st.subheader("Stage 2: Intrinsic Value & Quality Filter (IVP)")
    core_watchlist_input = st.text_input(
        "Core ETF Watchlist (Editable):", value=st.session_state.core_watchlist
    )
    st.session_state.core_watchlist = core_watchlist_input

    if core_watchlist_input.strip():
      tickers = [
          t.strip().upper() for t in core_watchlist_input.split(",") if t.strip()
      ]
      resolved_benchmarks = render_config_snippet_generator(tickers, config)

      if st.button("Run Intrinsic Valuation Check"):
        iv_results = []
        for t in tickers:
          try:
            stock = yf.Ticker(t)
            hist = stock.history(period="1y")
            if not hist.empty:
              p = float(hist["Close"].iloc[-1])
              sma200 = (
                  float(hist["Close"].rolling(200).mean().iloc[-1])
                  if len(hist) >= 200
                  else p
              )
              iv_results.append({
                  "Ticker": t,
                  "Price": round(p, 2),
                  "200 SMA": round(sma200, 2),
                  "Valuation Status": (
                      "Fair Value / Accumulate"
                      if p >= sma200
                      else "Deep Value / Discount"
                  ),
              })
          except Exception:
            pass
        if iv_results:
          st.dataframe(
              pd.DataFrame(iv_results), use_container_width=True, hide_index=True
          )

  with core_tab3:
    st.subheader("Stage 3: 200-Day Macro Trend Triggers")
    tickers = [
        t.strip().upper()
        for t in st.session_state.core_watchlist.split(",")
        if t.strip()
    ]
    if tickers:
      resolved_benchmarks = render_config_snippet_generator(tickers, config)
      trigger_rows = []
      for t in tickers:
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
            pd.DataFrame(trigger_rows), use_container_width=True, hide_index=True
        )
    else:
      st.info("No Core ETFs in watchlist. Run Stage 1 or add tickers in Stage 2.")

# ==========================================
# 3. 10% SATELLITE STOCK STRATEGY
# ==========================================
elif strategy_engine == "🚀 10% Satellite Stock Strategy":
  st.header("🚀 10% Satellite Stock Strategy Workflow")

  sat_tab1, sat_tab2 = st.tabs([
      "Stage 1: Dynamic Stock Screener",
      "Stage 2: Institutional Dip & Technical Evaluation",
  ])

  with sat_tab1:
    st.subheader("Stage 1: Scan Universe for Accumulation Candidates")
    st.markdown(
        "Starts completely blank. Run the dynamic screener below to discover"
        " qualified candidates."
    )

    if st.button("Run Dynamic Stock Screener", type="primary"):
      scan_universe = [
          "NVDA",
          "META",
          "AMZN",
          "MSFT",
          "AAPL",
          "GOOGL",
          "TSLA",
          "AVGO",
          "AMD",
          "NFLX",
      ]
      qualified = []
      with st.spinner("Scanning equities for volume and trend health..."):
        for t in scan_universe:
          try:
            df = yf.download(
                t, period="6mo", interval="1d", auto_adjust=True, progress=False
            )
            if not df.empty and len(df) > 50:
              c = df["Close"].squeeze()
              p = float(c.iloc[-1])
              sma50 = float(c.rolling(50).mean().iloc[-1])
              dist = (p - sma50) / sma50
              if -0.05 <= dist <= 0.05:
                qualified.append(t)
          except Exception:
            pass
      if qualified:
        st.session_state.satellite_scanned_tickers = ",".join(qualified)
        st.success(
            f"Discovered {len(qualified)} candidates and populated Stage 2!"
        )
      else:
        st.info(
            "No stocks met the strict 50 SMA threshold in this scan."
            " Alternatively, type tickers directly in Stage 2."
        )

  with sat_tab2:
    st.subheader("Stage 2: Institutional Dip & Technical Evaluation")
    sat_input = st.text_input(
        "Editable Candidate Watchlist (Modify before evaluation):",
        value=st.session_state.satellite_scanned_tickers,
        placeholder="e.g., NVDA, META, AMZN",
    )
    st.session_state.satellite_scanned_tickers = sat_input

    if sat_input.strip():
      tickers = [t.strip().upper() for t in sat_input.split(",") if t.strip()]
      resolved_benchmarks = render_config_snippet_generator(tickers, config)

      if st.button(
          "Run Institutional Dip & Technical Evaluation", type="primary"
      ):
        eval_rows = []
        for t in tickers:
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
            dist_50 = ((price - sma50) / sma50) * 100

            zone = (
                "Above 50 SMA (+)"
                if dist_50 >= 0
                else "Pullback Below 50 SMA (-)"
            )
            eval_rows.append({
                "Ticker": t,
                "Price": round(price, 2),
                "50 SMA Distance": f"{dist_50:+.2f}% ({zone})",
                "Structural Health": (
                    "Uptrend (Price > 200 SMA)"
                    if price > sma200
                    else "Caution"
                ),
            })
          except Exception as e:
            st.error(f"Error evaluating {t}: {e}")
        if eval_rows:
          st.dataframe(
              pd.DataFrame(eval_rows), use_container_width=True, hide_index=True
          )
    else:
      st.info(
          "Please run Stage 1 or enter candidate tickers in the box above to"
          " begin."
      )
