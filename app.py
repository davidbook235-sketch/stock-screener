import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

NIFTY50 = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","ICICIBANK.NS","INFY.NS",
    "HINDUNILVR.NS","ITC.NS","SBIN.NS","BHARTIARTL.NS","KOTAKBANK.NS",
    "LT.NS","AXISBANK.NS","ASIANPAINT.NS","MARUTI.NS","TITAN.NS",
    "SUNPHARMA.NS","ULTRACEMCO.NS","WIPRO.NS","NESTLEIND.NS","ONGC.NS",
    "NTPC.NS","POWERGRID.NS","M&M.NS","TATAMOTORS.NS","TATASTEEL.NS",
    "JSWSTEEL.NS","ADANIENT.NS","ADANIPORTS.NS","COALINDIA.NS","BAJFINANCE.NS",
    "BAJAJFINSV.NS","HCLTECH.NS","TECHM.NS","GRASIM.NS","INDUSINDBK.NS",
    "DRREDDY.NS","CIPLA.NS","EICHERMOT.NS","HEROMOTOCO.NS","BRITANNIA.NS",
    "DIVISLAB.NS","APOLLOHOSP.NS","HDFCLIFE.NS","SBILIFE.NS","BPCL.NS",
    "UPL.NS","BAJAJ-AUTO.NS","HINDALCO.NS","TATACONSUM.NS","LTIM.NS"
]

def get_data(symbol, period="6mo", interval="1d"):
    df = yf.download(symbol, period=period, interval=interval,
                     progress=False, auto_adjust=False)
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def add_indicators(df):
    df = df.copy()
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["RSI"] = rsi(df["Close"], 14)
    df["ATR"] = atr(df, 14)
    df["VolAvg20"] = df["Volume"].rolling(20).mean()

    df["MACD"] = df["Close"].ewm(span=12, adjust=False).mean() - df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()

    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    df["VWAP"] = (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()
    return df

def swing_signal(df):
    last = df.iloc[-1]
    score = 0
    reasons = []

    if last["Close"] > last["EMA20"] > last["EMA50"]:
        score += 1
        reasons.append("EMA20 > EMA50")
    if last["RSI"] > 55:
        score += 1
        reasons.append("RSI > 55")
    if last["MACD"] > last["MACD_Signal"]:
        score += 1
        reasons.append("MACD bullish")
    if last["Close"] > df["High"].rolling(20).max().iloc[-2]:
        score += 1
        reasons.append("20-day breakout")
    if last["Volume"] > last["VolAvg20"] * 1.5:
        score += 1
        reasons.append("Volume spike")

    signal = "BUY" if score >= 4 else "WATCH" if score >= 3 else "AVOID"
    entry = round(last["Close"], 2)
    sl = round(entry - 1.5 * last["ATR"], 2)
    target = round(entry + 3.0 * last["ATR"], 2)

    return {
        "Signal": signal, "Score": score, "Entry": entry,
        "StopLoss": sl, "Target": target, "Reasons": ", ".join(reasons)
    }

def intraday_signal(df):
    last = df.iloc[-1]
    score = 0
    reasons = []

    if last["Close"] > last["VWAP"]:
        score += 1
        reasons.append("Above VWAP")
    if last["EMA9"] > last["EMA21"]:
        score += 1
        reasons.append("EMA9 > EMA21")
    if last["RSI"] > 60:
        score += 1
        reasons.append("RSI > 60")
    if last["Volume"] > last["VolAvg20"] * 1.5:
        score += 1
        reasons.append("Volume spike")

    signal = "BUY" if score >= 3 else "WATCH" if score == 2 else "AVOID"
    entry = round(last["Close"], 2)
    sl = round(entry - 1.0 * last["ATR"], 2)
    target = round(entry + 1.5 * last["ATR"], 2)

    return {
        "Signal": signal, "Score": score, "Entry": entry,
        "StopLoss": sl, "Target": target, "Reasons": ", ".join(reasons)
    }

st.set_page_config(page_title="Indian Stock Screener", layout="wide")
st.title("📈 Indian Stock Market Screener")
st.caption("Swing + Intraday signals — Educational purpose only. Not SEBI registered advice.")

mode = st.sidebar.radio("Mode", ["Swing (Daily)", "Intraday (15m)"])

if mode.startswith("Swing"):
    period, interval = "6mo", "1d"
else:
    period, interval = "5d", "15m"

if st.button("Scan Nifty 50"):
    rows = []
    progress = st.progress(0)

    for i, sym in enumerate(NIFTY50):
        try:
            df = get_data(sym, period, interval)
            if len(df) < 50:
                continue
            df = add_indicators(df)
            res = swing_signal(df) if mode.startswith("Swing") else intraday_signal(df)
            res["Symbol"] = sym.replace(".NS", "")
            rows.append(res)
        except Exception:
            pass
        progress.progress((i + 1) / len(NIFTY50))

    if rows:
        out = pd.DataFrame(rows)
        cols = ["Symbol", "Signal", "Score", "Entry", "StopLoss", "Target", "Reasons"]
        st.dataframe(
            out[cols].sort_values(["Signal", "Score"], ascending=False),
            use_container_width=True
        )
    else:
        st.warning("Koi signal nahi mila ya data error aaya.")
