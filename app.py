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
      "criteria_thresholds": {
          "max_dist_from_50sma_pct": 0.04,
          "min_ud_vol_ratio": 1.15,
          "default_buffer_pct": 0.02,
          "default_rvol": 0.80,
      },
  }


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

# --- Sidebar Threshold & Parameter Editor ---
st.sidebar.header("⚙️ Institutional Criteria & RVOL")
thresholds = config.get("criteria_thresholds", {})

active_rvol = st.sidebar.slider(
    "Default RVOL Threshold",
    min_value=0.50,
    max_value=2.00,
    value=float(thresholds.get("default_rvol", 0.80)),
    step=0.05,
)
max_dist_sma = st.sidebar.slider(
    "Max Dist from 50 SMA (%)",
    min_value=0.01,
    max_value=0.10,
    value=float(thresholds.get("max_dist_from_50sma_pct", 0.04)),
    step=0.01,
)
min_ud_vol = st.sidebar.slider(
    "Min Up/Down Volume Ratio",
    min_value=1.00,
    max_value=2.00,
    value=float(thresholds.get("min_ud_vol_ratio", 1.15)),
    step=0.05,
)
buffer_pct = st.sidebar.slider(
    "Default Buffer (%)",
    min_value=0.00,
    max_value=0.05,
    value=float(thresholds.get("default_buffer_pct", 0.02)),
    step=0.005,
)

st.sidebar.divider()

# --- Sidebar Benchmark Mapping & Description Inspector ---
st.sidebar.header("🔍 Active Mappings & Descriptions")
benchmark_mapping = config.get("benchmark_mapping", {})

if benchmark_mapping:
  mapping_rows = []
  for ticker, details in benchmark_mapping.items():
    if isinstance(details, dict):
      bench = details.get("benchmark", "SPY")
      desc = details.get("description", "")
    else:
      bench = details
      desc = ""
    mapping_rows.append(
        {"Ticker": ticker, "Benchmark": bench, "Description": desc}
    )
  st.sidebar.dataframe(
      pd.DataFrame(mapping_rows), use_container_width=True, hide_index=True
  )
else:
  st.sidebar.info("No custom benchmark mappings found in config.")

with st.sidebar.expander("📖 System Architecture & Guide"):
  st.markdown("""
    * **Current Portfolio:** Live holdings monitor & multi-benchmark safe-harbor rotation matrix.
    * **90% Core ETF:** Macro relative strength ➔ Intrinsic Value ➔ 200-Day Trend Triggers.
    * **10% Satellite:** Custom screener ➔ Institutional dip evaluation ➔ Tactical watchlist execution.
    """)


# --- Helper: Resolve Benchmark & Description for Ticker ---
def get_resolved_benchmark_info(ticker):
  t = ticker.upper().strip()
  b_map = config.get("benchmark_mapping", {})
  if t in b_map:
    info = b_map[t]
    if isinstance(info, dict):
      return info.get("benchmark", "SPY"), info.get("description", "")
    return info, ""
  # Regional fallback mapping
  if t in ["INDA"]:
    return "EMXC", "iShares MSCI India ETF"
  if t in ["EWJ", "VGK"]:
    return "EFA", "Developed International / Europe / Japan"
  return "SPY", "Core US Benchmark"


# --- Benchmark Regime Helper ---
def get_benchmark_regime(ticker_symbol):
  bench, _ = get_resolved_benchmark_info(ticker_symbol)
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
  st.header("💼 Current Portfolio Holdings & Multi-Benchmark Rotation Matrix")
  st.markdown(
      "Real-time benchmark regime analysis governing rotation into risk-off safe"
      " harbors (`SCYB`, `JAAA`, `JPST`)."
  )

  curr_input = st.text_input(
      "Your Active Current Portfolio Holdings (Comma Separated):",
      placeholder="e.g., JAAA, JPST, SCHD, SPYI, VOO",
  )

  if curr_input.strip():
    holdings = [t.strip().upper() for t in curr_input.split(",") if t.strip()]

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
        regime, action = get_benchmark_regime(b)
        rot_data.append({
            "Benchmark": b,
            "Price": round(price, 2),
            "50 SMA": round(sma50, 2),
            "200 SMA": round(sma200, 2),
            "Regime Status": regime,
            "Recommended Action": action,
        })
      except Exception:
        pass

    if rot_data:
      st.dataframe(
          pd.DataFrame(rot_data), use_container_width=True, hide_index=True
      )

    st.subheader("2. Active Holdings Institutional & Technical Health")
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
          vol = df["Volume"].squeeze()
          price = float(c.iloc[-1])
          sma50 = float(c.rolling(50).mean().iloc[-1])
          sma200 = float(c.rolling(200).mean().iloc[-1])
          dist_200 = ((price - sma200) / sma200) * 100

          # RVOL & Volume Check
          avg_vol = float(vol.rolling(20).mean().iloc[-1])
          cur_vol = float(vol.iloc[-1])
          rvol = cur_vol / avg_vol if avg_vol > 0 else 1.0

          bench, desc = get_resolved_benchmark_info(t)
          regime, guidance = get_benchmark_regime(t)

          portfolio_results.append({
              "Ticker": t,
              "Description": desc,
              "Price": round(price, 2),
              "Benchmark": bench,
              "RVOL": round(rvol, 2),
              "Regime Status": regime,
              "% vs 200 SMA": f"{dist_200:+.2f}%",
              "Guidance": guidance,
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
      "Stage 1: Core Macro Universe Scan",
      "Stage 2: Intrinsic Value & Dip Filter",
      "Stage 3: 200-Day Trend Triggers",
  ])

  with core_tab1:
    st.subheader("Stage 1: Scan Global Macro Universe")
    selected_bench = st.selectbox(
        "Select Benchmark for Relative Strength Comparison",
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

  with core_tab2:
    st.subheader("Stage 2: Intrinsic Value & Institutional Dip Filter")
    core_watchlist_input = st.text_input(
        "Enter Core ETFs to Evaluate (Comma-Separated):",
        placeholder="e.g., SCHD, VOO, QQQI, SPYI",
    )

    if core_watchlist_input.strip():
      tickers = [
          t.strip().upper() for t in core_watchlist_input.split(",") if t.strip()
      ]
      if st.button("Run Intrinsic Valuation & Dip Check", type="primary"):
        iv_results = []
        for t in tickers:
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
                if p >= sma200 and abs(dist_50) <= max_dist_sma
                else (
                    "Deep Value / Discount"
                    if p < sma200
                    else "Extended / Caution"
                )
            )

            iv_results.append({
                "Ticker": t,
                "Price": round(p, 2),
                "50 SMA": round(sma50, 2),
                "200 SMA": round(sma200, 2),
                "RVOL": round(rvol, 2),
                "Valuation & Dip Status": val_status,
            })
          except Exception:
            pass
        if iv_results:
          st.dataframe(
              pd.DataFrame(iv_results), use_container_width=True, hide_index=True
          )

  with core_tab3:
    st.subheader("Stage 3: 200-Day Macro Trend Triggers")
    core_trig_input = st.text_input(
        "Enter Core ETFs for Trend Trigger Validation (Comma-Separated):",
        placeholder="e.g., SCHD, VOO, QQQI",
    )
    if core_trig_input.strip():
      tickers = [
          t.strip().upper() for t in core_trig_input.split(",") if t.strip()
      ]
      if st.button("Run Trend Trigger Audit", type="primary"):
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
              pd.DataFrame(trigger_rows),
              use_container_width=True,
              hide_index=True,
          )

# ==========================================
# 3. 10% SATELLITE STOCK STRATEGY
# ==========================================
elif strategy_engine == "🚀 10% Satellite Stock Strategy":
  st.header("🚀 10% Satellite Stock Strategy Workflow")

  sat_tab1, sat_tab2 = st.tabs([
      "Stage 1: Custom Stock Universe Scan",
      "Stage 2: Institutional Accumulation & Dip Evaluation",
  ])

  with sat_tab1:
    st.subheader("Stage 1: Scan Custom Equity Candidates")
    custom_scan_input = st.text_input(
        "Enter Custom Stock Tickers to Screen (Comma-Separated):",
        placeholder="e.g., NVDA, META, AMZN, MSFT, AAPL",
    )

    if st.button("Run Stock Screener", type="primary"):
      scan_universe = (
          [s.strip().upper() for s in custom_scan_input.split(",") if s.strip()]
          if custom_scan_input.strip()
          else []
      )

      if not scan_universe:
        st.warning("Please enter tickers above to scan your custom universe.")
      else:
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
                if abs(dist) <= max_dist_sma:
                  qualified.append(t)
            except Exception:
              pass
        if qualified:
          st.success(
              f"Discovered {len(qualified)} qualified candidates: "
              f"{', '.join(qualified)}"
          )
        else:
          st.info("No stocks met the strict 50 SMA distance threshold.")

  with sat_tab2:
    st.subheader(
        "Stage 2: Institutional Accumulation / Distribution & Dip Evaluation"
    )
    sat_input = st.text_input(
        "Enter Candidate Watchlist for Institutional Evaluation"
        " (Comma-Separated):",
        placeholder="e.g., NVDA, META, AMZN",
    )

    if sat_input.strip():
      tickers = [t.strip().upper() for t in sat_input.split(",") if t.strip()]

      if st.button(
          "Run Institutional Dip & Accumulation Evaluation", type="primary"
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
            vol = df["Volume"].squeeze()
            price = float(c.iloc[-1])
            sma50 = float(c.rolling(50).mean().iloc[-1])
            sma200 = float(c.rolling(200).mean().iloc[-1])
            dist_50 = ((price - sma50) / sma50) * 100

            # RVOL Calculation
            avg_vol = float(vol.rolling(20).mean().iloc[-1])
            cur_vol = float(vol.iloc[-1])
            rvol = cur_vol / avg_vol if avg_vol > 0 else 1.0

            # Accumulation vs Distribution check
            flow_status = (
                "🟢 Institutional Accumulation (RVOL > Threshold & Healthy Dip)"
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
      st.info("Please enter candidate tickers above to begin evaluation.")
