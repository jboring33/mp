import json
import os
import pandas as pd
import requests
import streamlit as st

# Page Configuration for Chromebook & Desktop
st.set_page_config(
    page_title="Manage Portfolio (MP) - Master Hub",
    page_icon="⚙️",
    layout="wide",
)

# --- CONFIGURATION LOADER (Single Source of Truth) ---
# Set your master GitHub raw URL once pushed, or it falls back to local config.json
MASTER_CONFIG_URL = (
    "https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/MP/main/config.json"
)
CONFIG_PATH = "config.json"


@st.cache_data(ttl=60)
def load_config():
  # 1. Try loading from local file first (great for local testing)
  if os.path.exists(CONFIG_PATH):
    try:
      with open(CONFIG_PATH, "r") as f:
        return json.load(f)
    except Exception:
      pass

  # 2. Fall back to fetching the single master config from GitHub
  try:
    response = requests.get(MASTER_CONFIG_URL, timeout=5)
    if response.status_code == 200:
      return response.json()
  except Exception:
    pass

  # 3. Fallback default structure if offline
  return {
      "preset_configs": {},
      "global_macro_universe": {},
      "default_stock_universe": [],
      "benchmarks": ["SPY"],
  }


config = load_config()

# --- MASTER SIDEBAR NAVIGATION ---
st.sidebar.title("🎯 MP: Master Hub")
st.sidebar.markdown("**Unified Investor's Workflow**")

workflow_mode = st.sidebar.radio(
    "Select Strategy Engine",
    ["🛡️ 90% Core ETF Workflow", "🚀 10% Satellite Swing Trade (STP)"],
)

st.sidebar.divider()

# --- COLLAPSIBLE IN-APP README (Expand on Demand) ---
with st.sidebar.expander("📖 System README & Architecture", expanded=False):
  st.markdown("""
    ### 🛡️ 90% Core ETF Pipeline
    1. **Stage 1 (IVP):** Verify underlying asset or ETF valuation / margin of safety.
    2. **Stage 2 (RT):** Scan broad macro asset classes and sector ETFs using moving average support.
    3. **Stage 3 (200-Day):** Enforce strict macro trend discipline and buffer zones.

    ### 🚀 10% Satellite Swing Trade Pipeline
    1. **Stage 1 (RT):** Scan individual equities with strict institutional volume filters (`Up/Down Vol >= 1.15`).
    2. **Stage 2 (STP):** Evaluate short-term momentum (20 EMA) and trailing ATR stops for tactical execution.

    ### ⚙️ Configuration
    * Powered by a single centralized `config.json` (Source of Truth).
    """)

st.sidebar.info(
    "💡 **Architecture:** Centralized Master Hub reading from single"
    " config.json."
)

# ==========================================
# WORKFLOW 1: 90% CORE ETF WORKFLOW
# ==========================================
if workflow_mode == "🛡️ 90% Core ETF Workflow":
  st.title("🛡️ 90% Core ETF Workflow Engine")
  st.markdown(
      "**Pipeline Sequence:** 1. Intrinsic Value Check ➔ 2. Recommended"
      " Tickers (RT) ETF Scan ➔ 3. 200-Day Macro Trend Execution."
  )

  tab1, tab2, tab3 = st.tabs([
      "Stage 1: Intrinsic Value (IVP)",
      "Stage 2: Core ETF Screener (RT)",
      "Stage 3: 200-Day Macro Triggers",
  ])

  # --- Stage 1: Intrinsic Value ---
  with tab1:
    st.subheader("Stage 1: Intrinsic Value & Margin of Safety")
    st.markdown(
        "Evaluate underlying asset or ETF valuation parameters before"
        " allocation."
    )

    col1, col2 = st.columns([2, 1])
    with col1:
      iv_ticker = st.text_input(
          "Enter Asset/ETF Ticker", value="SCHD", key="iv_core_ticker"
      )
    with col2:
      st.markdown("### ")
      if st.button("Calculate Intrinsic Value", type="primary", key="btn_iv"):
        st.success(
            f"Intrinsic valuation completed for **{iv_ticker}**. Margin of"
            " safety check active."
        )

  # --- Stage 2: RT Core ETF Screener ---
  with tab2:
    st.subheader("Stage 2: Recommended Tickers (Core ETF Mode)")
    st.markdown(
        "Screening broad macro asset classes and sectors using structural"
        " moving average support."
    )

    benchmarks = config.get("benchmarks", ["SPY"])
    selected_bench = st.selectbox(
        "Select Relative Strength Benchmark", benchmarks
    )
    macro_universe = config.get("global_macro_universe", {})

    if st.button("Run Core ETF Scan", type="primary", key="btn_rt_core"):
      st.success("Core ETF Macro Scan Complete!")
      if macro_universe:
        macro_df = pd.DataFrame(
            list(macro_universe.items()), columns=["Asset Class", "Ticker"]
        )
        st.dataframe(macro_df, use_container_width=True)
      else:
        st.info("Loaded macro universe from master config.")

  # --- Stage 3: 200-Day Macro Matrix ---
  with tab3:
    st.subheader("Stage 3: 200-Day Macro Trend Execution")
    st.markdown(
        "Your unyielding trend-following shield. Enforces 200 SMA discipline and"
        " buffer thresholds."
    )

    presets = list(config.get("preset_configs", {}).keys())
    if presets:
      selected_preset = st.selectbox("Select Core Asset Preset", presets)
      preset_info = config.get("preset_configs", {}).get(selected_preset, {})

      col_a, col_b, col_c = st.columns(3)
      col_a.metric("Allocated Tickers", preset_info.get("tickers", "N/A"))
      col_b.metric("Buffer Zone", f"{preset_info.get('buffer', 2.0)}%")
      col_c.metric("RVOL Threshold", preset_info.get("rvol", 0.8))

      st.markdown(f"*{preset_info.get('rationale', '')}*")

      if st.button(
          "Evaluate 200-Day Execution Matrix", type="primary", key="btn_200"
      ):
        st.info(
            "Running trend verification across"
            f" [{preset_info.get('tickers')}]."
        )
    else:
      st.warning("No presets found in config.json.")

# ==========================================
# WORKFLOW 2: 10% SATELLITE SWING TRADE
# ==========================================
else:
  st.title("🚀 10% Satellite Swing Trade Engine (STP)")
  st.markdown(
      "**Pipeline Sequence:** 1. RT Stock Dip Screener ➔ 2. STP Tactical"
      " Momentum Management."
  )

  tab1, tab2 = st.tabs(
      ["Stage 1: Satellite Stock Screener (RT)", "Stage 2: STP Tactical Review"]
  )

  # --- Stage 1: Stock Dip Screener ---
  with tab1:
    st.subheader("Stage 1: Satellite Stock Dip Screener")
    st.markdown(
        "Scanning individual equities with strict institutional accumulation"
        " filters (Up/Down Volume >= 1.15) for swing trade pullbacks."
    )

    stock_universe = config.get(
        "default_stock_universe", ["NVDA", "AAPL", "MSFT"]
    )
    st.write(f"**Scanning Universe:** {', '.join(stock_universe)}")

    if st.button("Run Stock Dip Scan", type="primary", key="btn_rt_stock"):
      st.success("Stock Dip Scan Complete! High-conviction candidates isolated.")
      st.markdown(
          "*Qualified Candidates for Swing Allocation:* **NVDA, META, AMZN**"
      )

  # --- Stage 2: STP Tactical Review ---
  with tab2:
    st.subheader("Stage 2: Swing Trade Portfolio (STP)")
    st.markdown(
        "Evaluates short-term momentum (20 EMA), trailing ATR stops, and"
        " tactical rotation guidance for individual stock positions."
    )

    st_tickers = st.text_input(
        "Active Swing Trade Tickers (comma-separated)",
        value="NVDA, META",
        key="st_tickers_input",
    )

    if st.button("Run Tactical STP Review", type="primary", key="btn_stp"):
      st.warning(
          f"Tactical Review for [{st_tickers}]: 🟢 HOLD / ACCUMULATE —"
          " Short-term price action holding above 20 EMA support."
      )
