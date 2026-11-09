"""
Manage Portfolio (MP) - TTT Asset Revesting & Sector Rotation Dashboard
----------------------------------------------------------------------
Framework: Python 3.11 + Streamlit
Built strictly around Chris Vermeulen's Technical Traders (TTT) top-down workflow:
1. Macro Market Gauge & VIX Risk Filter
2. Dynamic Sector & Asset Universe Momentum Scanning
3. 20-Day EMA & Institutional Whipsaw Signal Filtering
"""

import json
import os
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "whipsaw_params": {
        "rvol_threshold": 1.2,
        "max_dist_50sma_pct": 8.0,
        "min_up_down_vol_ratio": 1.1,
        "sma200_buffer_pct": 1.5,
        "vix_warning_level": 22.0,
        "momentum_lookback_days": 63,
    }
}

# Standard Institutional Sector & Asset Class Universe scanned by TTT models
SECTOR_UNIVERSE = {
    "XLK": "Technology Sector",
    "XLF": "Financial Sector",
    "XLE": "Energy Sector",
    "XLV": "Healthcare Sector",
    "XLI": "Industrials Sector",
    "XLP": "Consumer Staples Sector",
    "XLU": "Utilities Sector",
    "XLRE": "Real Estate Sector",
    "XLC": "Communication Services",
    "XLY": "Consumer Discretionary",
    "XLB": "Materials Sector",
    "IAU": "Gold / Precious Metals",
    "TLT": "Long-Term Treasuries (Defensive)",
}


def load_config():
  """Loads settings from config.json or initializes defaults."""
  if os.path.exists(CONFIG_FILE):
    try:
      with open(CONFIG_FILE, "r") as f:
        return json.load(f)
    except Exception:
      return DEFAULT_CONFIG
  return DEFAULT_CONFIG


def save_config(config_data):
  """Persists current state to config.json."""
  with open(CONFIG_FILE, "w") as f:
    json.dump(config_data, f, indent=4)


@st.cache_data(ttl=300)
def fetch_market_data(tickers):
  """Downloads 1-year historical price and volume data via yfinance."""
  all_tickers = list(set(tickers + ["SPY", "QQQ", "DIA", "^VIX"]))
  data = yf.download(
      all_tickers, period="1y", interval="1d", auto_adjust=True, progress=False
  )
  if isinstance(data.columns, pd.MultiIndex):
    close_prices = data["Close"]
    volumes = data["Volume"]
  else:
    close_prices = data[["Close"]]
    volumes = data[["Volume"]]
    close_prices.columns = all_tickers
    volumes.columns = all_tickers
  return close_prices.dropna(how="all"), volumes.dropna(how="all")


def evaluate_index_status(
    prices, benchmark_ticker, vix_level, vix_threshold=22.0
):
  """Determines BUY (Green), HOLD (Yellow), or SELL (Red) for major macro indexes."""
  if benchmark_ticker not in prices.columns:
    return "SELL", 0.0, 0.0

  series = prices[benchmark_ticker].dropna()
  current_price = series.iloc[-1]
  ema20 = series.ewm(span=20, adjust=False).mean().iloc[-1]
  sma50 = series.rolling(window=50).mean().iloc[-1]

  if current_price < ema20 or vix_level >= vix_threshold:
    status = "SELL"
  elif (
      current_price >= ema20
      and current_price >= sma50
      and vix_level < vix_threshold
  ):
    status = "BUY"
  else:
    status = "HOLD"

  return status, current_price, ema20


def evaluate_sector_asset(ticker, description, prices, volumes, params, macro_risk_off):
  """Audits a sector or asset class using TTT rules and institutional flow filters."""
  if ticker not in prices.columns:
    return {
        "Ticker": ticker,
        "Asset / Sector Name": description,
        "Status": "UNKNOWN",
        "Action": "No Data Available",
        "Reason": "Missing ticker history",
    }

  p_series = prices[ticker].dropna()
  v_series = volumes[ticker].dropna() if ticker in volumes.columns else None

  curr_price = p_series.iloc[-1]
  ema20 = p_series.ewm(span=20, adjust=False).mean().iloc[-1]
  sma50 = (
      p_series.rolling(window=50).mean().iloc[-1]
      if len(p_series) >= 50
      else curr_price
  )
  sma200 = (
      p_series.rolling(window=200).mean().iloc[-1]
      if len(p_series) >= 200
      else curr_price
  )

  # Macro Risk-Off / High VIX Trigger -> Command Capital to Move to Sidelines (Cash)
  if macro_risk_off and ticker not in ["IAU", "TLT"]:
    return {
        "Ticker": ticker,
        "Asset / Sector Name": description,
        "Price": f"${curr_price:.2f}",
        "20 EMA": f"${ema20:.2f}",
        "Status": "MOVE TO SIDELINES 💵",
        "Action": "Raise Cash / Capital Protection",
        "Reason": "Macro VIX / Market Gauge trigger mandates Sidelines",
    }

  # TTT Core Axiom: Below 20 EMA -> Immediate SELL / Exit
  if curr_price < ema20:
    return {
        "Ticker": ticker,
        "Asset / Sector Name": description,
        "Price": f"${curr_price:.2f}",
        "20 EMA": f"${ema20:.2f}",
        "Status": "SELL 🔴",
        "Action": "Exit Position / Avoid Entry",
        "Reason": "Price below 20 EMA trend filter",
    }

  # Whipsaw & Institutional Flow Checks
  reasons = []
  is_hold = False

  # 1. 200-Day SMA Buffer Check
  if curr_price < sma200 * (1 + params["sma200_buffer_pct"] / 100.0):
    is_hold = True
    reasons.append("Below 200 SMA buffer limit")

  # 2. Overextended Check (Max Distance from 50 SMA)
  dist_from_50 = ((curr_price - sma50) / sma50) * 100.0
  if dist_from_50 > params["max_dist_50sma_pct"]:
    is_hold = True
    reasons.append(f"Overextended ({dist_from_50:.1f}% from 50 SMA)")

  # 3. Volume Filters (if volume data is available)
  if v_series is not None and len(v_series) >= 20:
    recent_vol = v_series.iloc[-1]
    vol_20_avg = v_series.tail(20).mean()
    rvol = recent_vol / vol_20_avg if vol_20_avg > 0 else 1.0

    if rvol < params["rvol_threshold"]:
      is_hold = True
      reasons.append(f"Low RVOL ({rvol:.2f}x < {params['rvol_threshold']}x)")

    # Up/Down Volume Ratio (20-day approximation)
    returns = p_series.pct_change().tail(20)
    vols = v_series.tail(20)
    up_vol = vols[returns > 0].sum()
    down_vol = vols[returns < 0].sum()
    up_down_ratio = up_vol / down_vol if down_vol > 0 else 1.0

    if up_down_ratio < params["min_up_down_vol_ratio"]:
      is_hold = True
      reasons.append(
          f"Weak Up/Down Vol Ratio ({up_down_ratio:.2f} <"
          f" {params['min_up_down_vol_ratio']})"
      )

  if is_hold:
    status_label = "HOLD 🟡"
    action = "Caution / Await Volume Confirmation"
    reason_str = "; ".join(reasons)
  else:
    status_label = "BUY 🟢"
    action = "Strong Sector Leadership Active"
    reason_str = "All Trend & Flow Criteria Satisfied"

  return {
      "Ticker": ticker,
      "Asset / Sector Name": description,
      "Price": f"${curr_price:.2f}",
      "20 EMA": f"${ema20:.2f}",
      "Status": status_label,
      "Action": action,
      "Reason": reason_str,
  }


# -------------------------------------------------------------------------
# Streamlit Interface Implementation
# -------------------------------------------------------------------------
def main():
  st.set_page_config(
      page_title="Manage Portfolio (MP) — TTT Framework", layout="wide"
  )
  st.title(
      "📈 Manage Portfolio (MP) — Technical Traders Asset Revesting Dashboard"
  )

  # Load State Configuration
  config = load_config()
  w_params = config.get("whipsaw_params", DEFAULT_CONFIG["whipsaw_params"])

  # Sidebar: Institutional Flow & VIX Rules Controls
  st.sidebar.header("⚙️ Institutional Flow & VIX Rules")
  rvol_thresh = st.sidebar.slider(
      "Min RVOL Threshold", 0.8, 3.0, float(w_params["rvol_threshold"]), 0.1
  )
  max_dist = st.sidebar.slider(
      "Max Dist from 50 SMA (%)",
      3.0,
      20.0,
      float(w_params["max_dist_50sma_pct"]),
      0.5,
  )
  min_ratio = st.sidebar.slider(
      "Min Up/Down Vol Ratio",
      0.8,
      2.5,
      float(w_params["min_up_down_vol_ratio"]),
      0.1,
  )
  vix_thresh = st.sidebar.slider(
      "VIX Risk Threshold",
      15.0,
      40.0,
      float(w_params["vix_warning_level"]),
      1.0,
  )
  lookback = st.sidebar.slider(
      "Momentum Lookback (Days)",
      20,
      126,
      int(w_params.get("momentum_lookback_days", 63)),
      1,
  )

  updated_params = {
      "rvol_threshold": rvol_thresh,
      "max_dist_50sma_pct": max_dist,
      "min_up_down_vol_ratio": min_ratio,
      "sma200_buffer_pct": float(w_params.get("sma200_buffer_pct", 1.5)),
      "vix_warning_level": vix_thresh,
      "momentum_lookback_days": lookback,
  }
  if updated_params != w_params:
    config["whipsaw_params"] = updated_params
    save_config(config)

  # Download Market Data for Macro Indexes + Entire Sector Universe
  all_scan_tickers = list(SECTOR_UNIVERSE.keys())
  prices, volumes = fetch_market_data(all_scan_tickers)

  # VIX Volatility Indicator Check
  vix_level = (
      prices["^VIX"].iloc[-1] if "^VIX" in prices.columns else 15.0
  )
  vix_risk_off = vix_level >= vix_thresh

  # 1. Macro Environment Gauges Section (TTT Market Gauge)
  st.subheader(
      "1. U.S. Macro Environment Gauges (Market Gauge & VIX Risk Filter)"
  )
  col_vix, col_spy, col_qqq, col_dia = st.columns(4)

  spy_status, spy_p, spy_e = evaluate_index_status(
      prices, "SPY", vix_level, vix_thresh
  )
  qqq_status, qqq_p, qqq_e = evaluate_index_status(
      prices, "QQQ", vix_level, vix_thresh
  )
  dia_status, dia_p, dia_e = evaluate_index_status(
      prices, "DIA", vix_level, vix_thresh
  )

  with col_vix:
    vix_color = "off" if not vix_risk_off else "inverse"
    st.metric(
        label="CBOE Volatility Index (^VIX)",
        value=f"{vix_level:.2f}",
        delta="NORMAL (Risk-On)" if not vix_risk_off else "ELEVATED (Risk-Off)",
        delta_color=vix_color,
    )
    st.markdown(
        f"**VIX Rule:** `{'SPIKE > ' + str(vix_thresh) + ' -> EQUITY RISK-OFF' if vix_risk_off else 'Normal Range'}`"
    )

  with col_spy:
    st.metric(
        label="S&P 500 (SPY)",
        value=f"${spy_p:.2f}",
        delta=f"20 EMA: ${spy_e:.2f}",
    )
    st.markdown(f"**Status:** `{spy_status}`")

  with col_qqq:
    st.metric(
        label="Nasdaq 100 (QQQ)",
        value=f"${qqq_p:.2f}",
        delta=f"20 EMA: ${qqq_e:.2f}",
    )
    st.markdown(f"**Status:** `{qqq_status}`")

  with col_dia:
    st.metric(
        label="Dow Jones (DIA)",
        value=f"${dia_p:.2f}",
        delta=f"20 EMA: ${dia_e:.2f}",
    )
    st.markdown(f"**Status:** `{dia_status}`")

  if vix_risk_off:
    st.warning(
        f"⚠️ **VIX Risk Alert:** VIX is at `{vix_level:.2f}` (above threshold"
        f" `{vix_thresh}`). Broad equity markets face downside pressure; equity"
        " exposure should be reduced and capital moved to **Sidelines (Cash)**."
    )

  st.markdown("---")

  # 2. Sector & Asset Class Dynamic Scan & Ranking Table
  st.subheader(
      "2. Institutional Sector & Asset Class Scan (Relative Momentum Ranking)"
  )

  results = []
  for ticker, desc in SECTOR_UNIVERSE.items():
    res = evaluate_sector_asset(
        ticker, desc, prices, volumes, updated_params, vix_risk_off
    )
    # Calculate Relative Momentum (Rate of Change over lookback window)
    if ticker in prices.columns and len(prices[ticker].dropna()) >= lookback:
      roc = (
          (prices[ticker].iloc[-1] - prices[ticker].iloc[-lookback])
          / prices[ticker].iloc[-lookback]
      ) * 100.0
      res["Momentum (%)"] = round(float(roc), 2)
    else:
      res["Momentum (%)"] = 0.0
    results.append(res)

  df_results = pd.DataFrame(results)

  # Sort by Momentum % descending to highlight leading sectors
  if "Momentum (%)" in df_results.columns:
    df_results = df_results.sort_values(by="Momentum (%)", ascending=False)

  # Reorder columns for optimal readability
  cols = [
      "Ticker",
      "Asset / Sector Name",
      "Price",
      "20 EMA",
      "Momentum (%)",
      "Status",
      "Action",
      "Reason",
  ]
  df_results = df_results[[c for c in cols if c in df_results.columns]]

  # Apply visual styling for status column
  def style_status(val):
    if "BUY" in str(val):
      return "background-color: #d4edda; color: #155724; font-weight: bold;"
    elif "HOLD" in str(val):
      return "background-color: #fff3cd; color: #856404; font-weight: bold;"
    elif "SELL" in str(val):
      return "background-color: #f8d7da; color: #721c24; font-weight: bold;"
    elif "SIDELINES" in str(val):
      return "background-color: #cce5ff; color: #004085; font-weight: bold;"
    return ""

  styled_df = df_results.style.map(style_status, subset=["Status"])
  st.dataframe(styled_df, use_container_width=True)


if __name__ == "__main__":
  main()
