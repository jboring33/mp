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

# --- Sidebar Asset Class Threshold Profiles & Sliders ---
st.sidebar.header("⚙️ Institutional Criteria & RVOL Profiles")

asset_profiles = config.get(
    "asset_class_thresholds",
    {
        "Broad Market Core": {
            "max_dist_from_50sma_pct": 0.04,
            "min_ud_vol_ratio": 1.15,
            "default_buffer_pct": 0.02,
            "default_rvol": 0.80,
        },
        "Dividends & Value": {
            "max_dist_from_50sma_pct": 0.03,
            "min_ud_vol_ratio": 1.10,
            "default_buffer_pct": 0.015,
            "default_rvol": 0.75,
        },
        "Covered Calls & Income": {
            "max_dist_from_50sma_pct": 0.025,
            "min_ud_vol_ratio": 1.05,
            "default_buffer_pct": 0.01,
            "default_rvol": 0.70,
        },
        "Fixed Income & Safe Harbors": {
            "max_dist_from_50sma_pct": 0.01,
            "min_ud_vol_ratio": 1.00,
            "default_buffer_pct": 0.005,
            "default_rvol": 0.50,
        },
        "Growth & Satellite Equities": {
            "max_dist_from_50sma_pct": 0.06,
            "min_ud_vol_ratio": 1.25,
            "default_buffer_pct": 0.03,
            "default_rvol": 1.10,
        },
    },
)

selected_profile_name = st.sidebar.selectbox(
    "Asset Class / Strategy Profile:", list(asset_profiles.keys())
)
selected_profile = asset_profiles.get(
    selected_profile_name, list(asset_profiles.values())[0]
)

active_rvol = st.sidebar.slider(
    "Target RVOL Threshold",
    min_value=0.40,
    max_value=2.00,
    value=float(selected_profile.get("default_rvol", 0.80)),
    step=0.05,
)
max_dist_sma = st.sidebar.slider(
    "Max Dist from 50 SMA (%)",
    min_value=0.005,
    max_value=0.100,
    value=float(selected_profile.get("max_dist_from_50sma_pct", 0.04)),
    step=0.005,
    format="%.3f",
)
min_ud_vol = st.sidebar.slider(
    "Min Up/Down Volume Ratio",
    min_value=1.00,
    max_value=2.00,
    value=float(selected_profile.get("min_ud_vol_ratio", 1.15)),
    step=0.05,
)
buffer_pct = st.sidebar.slider(
    "200-Day Buffer (%)",
    min_value=0.000,
    max_value=0.050,
    value=float(selected_profile.get("default_buffer_pct", 0.02)),
    step=0.005,
    format="%.3f",
)

st.sidebar.divider()

# --- Sidebar Benchmark Mapping & Flyover Description Inspector ---
st.sidebar.header("🔍 Active Mappings")
benchmark_mapping = config.get("benchmark_mapping", {})
bench_descriptions = config.get(
    "benchmark_descriptions",
    {
        "SPY": "SPDR S&P 500 ETF Trust (US Large Cap Core)",
        "QQQ": "Invesco QQQ Trust (US Tech & Growth)",
        "DIA": "SPDR Dow Jones Industrial Average ETF (US Value & Mega Cap)",
        "IWM": "iShares Russell 2000 ETF (US Small Cap)",
        "EFA": "iShares MSCI EAFE ETF (Developed International)",
        "EMXC": "iShares MSCI Emerging Markets ex China ETF",
    },
)

if benchmark_mapping:
  mapping_rows = []
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
    flyover_label = f"Ticker: {t_desc} | Benchmark: {b_desc}"

    mapping_rows.append({
        "Ticker": ticker,
        "Assigned Benchmark": bench,
        "Asset Class": asset_cls,
        "Details (Flyover)": flyover_label,
    })

  st.sidebar.dataframe(
      pd.DataFrame(mapping_rows),
      use_container_width=True,
      hide_index=True,
      column_config={
          "Ticker": st.column_config.TextColumn("Ticker", width="small"),
          "Assigned Benchmark": st.column_config.TextColumn(
              "Benchmark", width="small"
          ),
          "Asset Class": st.column_config.TextColumn(
              "Asset Class", width="medium"
          ),
          "Details (Flyover)": st.column_config.TextColumn(
              "Info (Hover)", help="Full ticker and benchmark descriptions"
          ),
      },
  )
else:
  st.sidebar.info("No custom benchmark mappings found in config.")

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

with st.sidebar.expander("📖 System Architecture & Guide"):
  st.markdown("""
    * **Current Portfolio:** Live holdings monitor & multi-benchmark safe-harbor rotation matrix.
    * **90% Core ETF:** Macro relative strength ➔ Intrinsic Value ➔ 200-Day Trend Triggers.
    * **10% Satellite:** Custom screener ➔ Institutional dip evaluation ➔ Tactical watchlist execution.
    """)


# --- Helper: Resolve Benchmark & Dual Description for Ticker ---
def get_resolved_benchmark_info(ticker):
  t = ticker.upper().strip()
  b_map = config.get("benchmark_mapping", {})
  b_desc_map = config.get("benchmark_descriptions", bench_descriptions)

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
        b_desc_map.get
