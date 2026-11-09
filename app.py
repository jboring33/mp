"""
Manage Portfolio (MP) - Institutional Flow & Asset Revesting Dashboard
---------------------------------------------------------------------
Framework: Python 3.11 + Streamlit
Built around Chris Vermeulen's Technical Traders (TTT) top-down workflow:
1. Macro Market Gauges (SPY, QQQ, DIA, ^VIX) evaluated on WEEKLY trends
   (10-week & 30-week EMAs) to eliminate daily noise and target low turnover.
2. 2nd-Tier Institutional Flow Engine:
   - Equal-Weighted vs. Cap-Weighted Ratio Analysis (RSP/SPY)
   - Intermarket Relative Strength Ratios (XLY/XLP, SPHB/SPLV, IWM/SPY, IAU/TLT)
   - Institutional Sub-Sectors (SMH, IGV, CIBR, KRE)
3. Daily 20 EMA Trailing Stops & RVOL/Overextended Whipsaw Filters.

Persistent state is maintained via `config.json`.
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
        "vix_warning_level": 22.0,
        "momentum_lookback_days": 63,
    }
}

# Categorized Sector & Asset Class Mapping by Benchmark Engine
INDEX_MAPPINGS = {
    # Broad S&P 500 Sectors (SPY)
    "XLK": {"name": "Technology SPDR", "benchmark": "SPY", "type": "Sector"},
    "XLF": {"name": "Financials SPDR", "benchmark": "SPY", "type": "Sector"},
    "XLE": {"name": "Energy SPDR", "benchmark": "SPY", "type": "Sector"},
    "XLV": {"name": "Healthcare SPDR", "benchmark": "SPY", "type": "Sector"},
    "XLI": {"name": "Industrials SPDR", "benchmark": "SPY", "type": "Sector"},
    "XLP": {"name": "Consumer Staples SPDR", "benchmark": "SPY", "type": "Sector"},
    "XLU": {"name": "Utilities SPDR", "benchmark": "SPY", "type": "Sector"},
    "XLRE": {"name": "Real Estate SPDR", "benchmark": "SPY", "type": "Sector"},
    "XLC": {"name": "Communication Services", "benchmark": "SPY", "type": "Sector"},
    "XLY": {"name": "Consumer Discretionary", "benchmark": "SPY", "type": "Sector"},
    "XLB": {"name": "Materials SPDR", "benchmark": "SPY", "type": "Sector"},
    # Institutional Sub-Sectors & Leadership Triggers
    "SMH": {"name": "Semiconductors ETF", "benchmark": "QQQ", "type": "Sub-Sector"},
    "IGV": {"name": "Software & Cloud ETF", "benchmark": "QQQ", "type": "Sub-Sector"},
    "CIBR": {"name": "Cybersecurity ETF", "benchmark": "QQQ", "type": "Sub-Sector"},
    "KRE": {"name": "Regional Banking ETF", "benchmark": "DIA", "type": "Sub-Sector"},
    # Independent Commodities & Safe-Havens
    "IAU": {"name": "Gold / Precious Metals", "benchmark": "INDEPENDENT", "type": "Asset"},
    "TLT": {"name": "Long-Term Treasuries", "benchmark": "INDEPENDENT", "type": "Asset"},
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
  """Downloads daily and weekly price/volume data via yfinance."""
  all_tickers = list(
      set(
          tickers
          + [
              "SPY",
              "QQQ",
              "DIA",
              "^VIX",
              "RSP",
              "XLY",
              "XLP",
              "SPHB",
              "SPLV",
              "IWM",
              "IAU",
              "TLT",
          ]
      )
  )

  d_data = yf.download(
      all_tickers, period="1y", interval="1d", auto_adjust=True, progress=False
  )
  w_data = yf.download(
      all_tickers, period="2y", interval="1wk", auto_adjust=True, progress=False
  )

  if isinstance(d_data.columns, pd.MultiIndex):
    daily_close = d_data["Close"]
    daily_vol = d_data["Volume"]
    weekly_close = w_data["Close"]
  else:
    daily_close = d_data[["Close"]]
    daily_vol = d_data[["Volume"]]
    weekly_close = w_data[["Close"]]
    daily_close.columns = all_tickers
    daily_vol.columns = all_tickers
    weekly_close.columns = all_tickers

  return (
      daily_close.dropna(how="all"),
      daily_vol.dropna(how="all"),
      weekly_close.dropna(how="all"),
  )


def evaluate_macro_gauge_weekly(
    weekly_prices, benchmark_ticker, vix_level, vix_threshold=22.0
):
  """Determines Macro Risk Status using WEEKLY charts (10 & 30-week EMAs)."""
  if benchmark_ticker not in weekly_prices.columns:
    return "SELL", 0.0, 0.0

  w_series = weekly_prices[benchmark_ticker].dropna()
  curr_w_price = w_series.iloc[-1]
  ema10_w = w_series.ewm(span=10, adjust=False).mean().iloc[-1]
  ema30_w = w_series.ewm(span=30, adjust=False).mean().iloc[-1]

  if curr_w_price < ema10_w or vix_level >= vix_threshold:
    status = "RISK-OFF 🔴"
  elif curr_w_price >= ema10_w and ema10_w >= ema30_w:
    status = "RISK-ON 🟢"
  else:
    status = "CAUTION 🟡"

  return status, curr_w_price, ema10_w


def evaluate_ratio_pair(daily_prices, num_ticker, den_ticker, lookback=20):
  """Evaluates an intermarket ratio pair (Numerator / Denominator) for relative strength trends."""
  if (
      num_ticker not in daily_prices.columns
      or den_ticker not in daily_prices.columns
  ):
    return {"ratio": 0.0, "roc_20": 0.0, "signal": "N/A"}

  ratio_series = (
      daily_prices[num_ticker].dropna() / daily_prices[den_ticker].dropna()
  ).dropna()
  if len(ratio_series) < lookback:
    return {"ratio": 0.0, "roc_20": 0.0, "signal": "N/A"}

  curr_ratio = ratio_series.iloc[-1]
  prev_ratio = ratio_series.iloc[-lookback]
  roc_20 = ((curr_ratio - prev_ratio) / prev_ratio) * 100.0

  ema20 = ratio_series.ewm(span=20, adjust=False).mean().iloc[-1]
  signal = "BULLISH 🟢" if curr_ratio >= ema20 else "BEARISH 🔴"

  return {
      "ratio": round(float(curr_ratio), 4),
      "roc_20": round(float(roc_20), 2),
      "signal": signal,
  }


def evaluate_sector_asset(
    ticker,
    info,
    daily_prices,
    daily_vols,
    params,
    macro_statuses,
    vix_risk_off,
):
  """Audits an individual sector/sub-sector applying benchmark alignment, 20-day EMA rules, and flow filters."""
  if ticker not in daily_prices.columns:
    return {
        "Ticker": ticker,
        "Name": info["name"],
        "Benchmark": info["benchmark"],
        "Status": "UNKNOWN",
        "Reason": "No Data",
    }

  p_series = daily_prices[ticker].dropna()
  v_series = (
      daily_vols[ticker].dropna() if ticker in daily_vols.columns else None
  )

  curr_price = p_series.iloc[-1]
  ema20 = p_series.ewm(span=20, adjust=False).mean().iloc[-1]
  sma50 = (
      p_series.rolling(window=50).mean().iloc[-1]
      if len(p_series) >= 50
      else curr_price
  )

  benchmark = info["benchmark"]
  bench_status = macro_statuses.get(benchmark, "RISK-ON 🟢")

  if (
      "RISK-OFF" in bench_status or vix_risk_off
  ) and benchmark != "INDEPENDENT":
    return {
        "Ticker": ticker,
        "Name": info["name"],
        "Benchmark": benchmark,
        "Price": f"${curr_price:.2f}",
        "20 EMA": f"${ema20:.2f}",
        "Status": "SIDELINES 💵",
        "Action": "Move Capital to Cash",
        "Reason": f"Governing Index ({benchmark}) or VIX trigger is Risk-Off",
    }

  if curr_price < ema20:
    return {
        "Ticker": ticker,
        "Name": info["name"],
        "Benchmark": benchmark,
        "Price": f"${curr_price:.2f}",
        "20 EMA": f"${ema20:.2f}",
        "Status": "SELL 🔴",
        "Action": "Exit Position / Avoid Entry",
        "Reason": "Price below daily 20 EMA trailing filter",
    }

  reasons = []
  is_hold = False

  dist_from_50 = ((curr_price - sma50) / sma50) * 100.0
  if dist_from_50 > params["max_dist_50sma_pct"]:
    is_hold = True
    reasons.append(f"Overextended ({dist_from_50:.1f}% from 50 SMA)")

  if v_series is not None and len(v_series) >= 20:
    recent_vol = v_series.iloc[-1]
    vol_20_avg = v_series.tail(20).mean()
    rvol = recent_vol / vol_20_avg if vol_20_avg > 0 else 1.0
    if rvol < params["rvol_threshold"]:
      is_hold = True
      reasons.append(f"Low RVOL ({rvol:.2f}x < {params['rvol_threshold']}x)")

  if is_hold:
    status_label = "HOLD 🟡"
    action = "Caution / Await Confirmation"
    reason_str = "; ".join(reasons)
  else:
    status_label = "BUY 🟢"
    action = "Strong Technical Leadership Active"
    reason_str = "All Macro & Trend Criteria Satisfied"

  return {
      "Ticker": ticker,
      "Name": info["name"],
      "Benchmark": benchmark,
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

  # Sidebar Controls
  st.sidebar.header("⚙️ Institutional Risk & VIX Thresholds")
  vix_thresh = st.sidebar.slider(
      "VIX Risk Threshold",
      15.0,
      40.0,
      float(w_params["vix_warning_level"]),
      1.0,
  )
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
      "min_up_down_vol_ratio": float(w_params.get("min_up_down_vol_ratio", 1.1)),
      "vix_warning_level": vix_thresh,
      "momentum_lookback_days": lookback,
  }
  if updated_params != w_params:
    config["whipsaw_params"] = updated_params
    save_config(config)

  # Fetch Daily & Weekly Market Data
  all_tickers = list(INDEX_MAPPINGS.keys())
  daily_prices, daily_vols, weekly_prices = fetch_market_data(all_tickers)

  # VIX Volatility Filter
  vix_level = (
      daily_prices["^VIX"].iloc[-1] if "^VIX" in daily_prices.columns else 15.0
  )
  vix_risk_off = vix_level >= vix_thresh

  # 1. Macro Environment Gauges (Weekly Smoothing Engine)
  st.subheader(
      "1. U.S. Macro Market Gauges (Weekly Trend Smoothing — Low Turnover"
      " Engine)"
  )
  col_vix, col_spy, col_qqq, col_dia = st.columns(4)

  spy_status, spy_p, spy_e = evaluate_macro_gauge_weekly(
      weekly_prices, "SPY", vix_level, vix_thresh
  )
  qqq_status, qqq_p, qqq_e = evaluate_macro_gauge_weekly(
      weekly_prices, "QQQ", vix_level, vix_thresh
  )
  dia_status, dia_p, dia_e = evaluate_macro_gauge_weekly(
      weekly_prices, "DIA", vix_level, vix_thresh
  )

  macro_statuses = {"SPY": spy_status, "QQQ": qqq_status, "DIA": dia_status}

  with col_vix:
    vix_color = "off" if not vix_risk_off else "inverse"
    st.metric(
        label="CBOE Volatility Index (^VIX)",
        value=f"{vix_level:.2f}",
        delta="NORMAL (Risk-On)" if not vix_risk_off else "ELEVATED (Risk-Off)",
        delta_color=vix_color,
    )
    st.markdown(
        f"**VIX Trigger:** `{'SPIKE > ' + str(vix_thresh) + ' -> SIDELINES' if vix_risk_off else 'Normal Range'}`"
    )

  with col_spy:
    st.metric(
        label="S&P 500 (SPY)",
        value=f"${spy_p:.2f}",
        delta=f"10-Wk EMA: ${spy_e:.2f}",
    )
    st.markdown(f"**Weekly Macro Status:** `{spy_status}`")

  with col_qqq:
    st.metric(
        label="Nasdaq 100 (QQQ)",
        value=f"${qqq_p:.2f}",
        delta=f"10-Wk EMA: ${qqq_e:.2f}",
    )
    st.markdown(f"**Weekly Macro Status:** `{qqq_status}`")

  with col_dia:
    st.metric(
        label="Dow Jones (DIA)",
        value=f"${dia_p:.2f}",
        delta=f"10-Wk EMA: ${dia_e:.2f}",
    )
    st.markdown(f"**Weekly Macro Status:** `{dia_status}`")

  st.markdown("---")

  # 2. Institutional Money Flow & Intermarket Ratio Engine
  st.subheader("2. Institutional Money Flow & Intermarket Ratio Engine")
  st.caption(
      "Tracks real capital rotation, market breadth, and risk sentiment beyond"
      " simple market-cap weighted sectors."
  )

  col_rsp, col_risk, col_beta, col_gold = st.columns(4)

  rsp_spy = evaluate_ratio_pair(daily_prices, "RSP", "SPY")
  xly_xlp = evaluate_ratio_pair(daily_prices, "XLY", "XLP")
  sphb_splv = evaluate_ratio_pair(daily_prices, "SPHB", "SPLV")
  iau_tlt = evaluate_ratio_pair(daily_prices, "IAU", "TLT")

  with col_rsp:
    st.metric(
        label="Market Breadth (RSP / SPY)",
        value=f"{rsp_spy['ratio']}",
        delta=f"20D ROC: {rsp_spy['roc_20']}%",
    )
    st.markdown(
        f"**Flow:** `{rsp_spy['signal']}`  \n*(Equal-Weight vs Cap-Weight)*"
    )

  with col_risk:
    st.metric(
        label="Risk Appetite (XLY / XLP)",
        value=f"{xly_xlp['ratio']}",
        delta=f"20D ROC: {xly_xlp['roc_20']}%",
    )
    st.markdown(
        f"**Flow:** `{xly_xlp['signal']}`  \n*(Discretionary vs Staples)*"
    )

  with col_beta:
    st.metric(
        label="Beta Profile (SPHB / SPLV)",
        value=f"{sphb_splv['ratio']}",
        delta=f"20D ROC: {sphb_splv['roc_20']}%",
    )
    st.markdown(
        f"**Flow:** `{sphb_splv['signal']}`  \n*(High Beta vs Low Vol)*"
    )

  with col_gold:
    st.metric(
        label="Monetary Hedge (IAU / TLT)",
        value=f"{iau_tlt['ratio']}",
        delta=f"20D ROC: {iau_tlt['roc_20']}%",
    )
    st.markdown(f"**Flow:** `{iau_tlt['signal']}`  \n*(Gold vs Bonds)*")

  st.markdown("---")

  # 3. Sector & Sub-Sector Dynamic Scan & Benchmark Audit
  st.subheader(
      "3. Sector & Sub-Sector Audit (Relative Momentum & Benchmark Alignment)"
  )

  results = []
  for ticker, info in INDEX_MAPPINGS.items():
    res = evaluate_sector_asset(
        ticker,
        info,
        daily_prices,
        daily_vols,
        updated_params,
        macro_statuses,
        vix_risk_off,
    )
    if (
        ticker in daily_prices.columns
        and len(daily_prices[ticker].dropna()) >= lookback
    ):
      roc = (
          (daily_prices[ticker].iloc[-1] - daily_prices[ticker].iloc[-lookback])
          / daily_prices[ticker].iloc[-lookback]
      ) * 100.0
      res["Momentum (%)"] = round(float(roc), 2)
    else:
      res["Momentum (%)"] = 0.0
    results.append(res)

  df_results = pd.DataFrame(results)

  if "Momentum (%)" in df_results.columns:
    df_results = df_results.sort_values(by="Momentum (%)", ascending=False)

  cols = [
      "Ticker",
      "Name",
      "Benchmark",
      "Price",
      "20 EMA",
      "Momentum (%)",
      "Status",
      "Action",
      "Reason",
  ]
  df_results = df_results[[c for c in cols if c in df_results.columns]]

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
